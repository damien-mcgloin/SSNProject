# attrgetter is used in the traffic monitor below
from operator import attrgetter

# Basic imports for Ryu
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
import ryu.ofproto.ofproto_v1_3_parser as parser
import ryu.ofproto.ofproto_v1_3 as ofproto
from ryu.lib.packet import packet
from ryu.lib.packet import ether_types

# The line below includes an additional tcp import used for counting and redirecting tcp traffic
from ryu.lib.packet import ethernet, arp, ipv4, ipv6, tcp
# hub is used for adding ten second delay for gathering port stats
from ryu.lib import hub

# cockpit import allows for the use of the program_flow function used for adding flow rules
from cockpit import CockpitApp
from netaddr import IPAddress, IPNetwork

# OrderedDict is used in traffic monitor for storing packet information
from collections import OrderedDict

ETHERTYPES = {2048: "IPv4", 2054: "ARP", 34525: "IPv6"}
L4PROTO = {1: "ICMP", 4: "IP-in-IP", 6: "TCP", 17: "UDP"}

class LearningSwitch(CockpitApp):
    ## Initialize SDN-App
    def __init__(self, *args, **kwargs):
        super(LearningSwitch, self).__init__(*args, **kwargs)
        # initalize mac address table
        self.mac_to_port = {}

        # used as part of the traffic monitor
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

        # used for storing ip addresses and syn packets sent and syn ack packets received per ip address
        self.packets_by_ip = dict()

        # used for storing total transmitted packets on network every ten seconds
        self.packets_per_sec = OrderedDict()
        self.pkt_count = {}

        # used for gathering number of TCP, SYN and ACK packets transmitted
        self.total_packets = 0
        self.syn_counter = 0
        self.ack_counter = 0

        # used for storing list of verified users so they are no longer challenged
        self.trusted_users = []

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    # this function issues a request for information for the switch every ten seconds
    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)

    # OFPP_ANY is used to ensure data on all ports is collected
    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    #provides list of OFPPortstats and is also used to redirect TCP traffic after a threshold is reached
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        datapath = ev.msg.datapath
        #packets = {}

        self.logger.info('\ndatapath            port   '
                         'rx-pkts  rx-bytes  rx-error  '
                         'tx-pkts  tx-bytes  tx-error  dur-sec')
        self.logger.info('_______________________________'
                         '_______________________________'
                         '_______________________________')

        # data requested includes received and transmitted packet counts and port numbers
        # code is similar to that seen in ryubook documentation but adapted to include duration in seconds
        # that the ports have been monitored
        for stat in sorted(body, key=attrgetter('port_no')):
            self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d %8d',
                            ev.msg.datapath.id, stat.port_no,
                            stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                            stat.tx_packets, stat.tx_bytes, stat.tx_errors,
                            stat.duration_sec)

            # OrderedDict is used to store packet count and duration_sec
            # OrderedDict was selected as it remembers the order entries were added
            # new entry is added every ten seconds
            if stat.tx_packets and stat.duration_sec not in self.packets_per_sec:
                self.packets_per_sec[stat.tx_packets] = stat.duration_sec

            # As the list takes time to fill with entries to fill it this will
            # allow for an immediate response if the application has just been initialized
            # and a high volume of traffic is sent
            if stat.duration_sec < 300 and stat.tx_packets > 5000:
                match = parser.OFPMatch(
                        eth_type=0x0800,
                        ip_proto=6)
                action = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
                self.program_flow(datapath, match, action, priority=100, idle_timeout=10, hard_timeout=0)

            # list created to store the newest entry. error handling used to prevent error when the application starts
        try:
            self.one = list(self.packets_per_sec.items())[-1]
            #print(self.one)
        except IndexError:
            self.one = 'null'

            # list created to store a previous entry
        try:
            self.two = list(self.packets_per_sec.items())[-5]
            #print(self.two)
        except IndexError:
            self.two = 'null'

            # variable used to check if there has been a recent spike in traffic on the network
        try:
            self.count = self.one[0] - self.two[0]
            #print(self.count)
        except TypeError:
            pass

            # if a traffic spike occurs tcp traffic will now be directed to the controller
        try:
            if self.count > 1000:
                match = parser.OFPMatch(
                        eth_type=0x0800,
                        ip_proto=6)
                action = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
                self.program_flow(datapath, match, action, priority=100, idle_timeout=10, hard_timeout=0)
        except AttributeError:
            pass

        # this will remove entries from the start of the list as it would otherwise store large amounts of
        # redundant data
        if len(self.packets_per_sec) > 8:
            self.packets_per_sec.popitem(last=False)

        #print(self.packets_per_sec)

    def debug_output(self, dp, pkt, in_port):
        eth = pkt.get_protocol(ethernet.ethernet)

        self.pkt_count[dp.id] += 1

        ## Info: Packet-in / Ethernet packet
        print("/// [Switch {}]: PACKET-IN (#{}) on port: {}".format(dp.id, self.pkt_count[dp.id], in_port))
        print("      SRC: {}, DST: {} --> {}".format(eth.src, eth.dst, ETHERTYPES[eth.ethertype]))

#        Info: IP Packet
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            # get_protocol method obtains object corresponding to the respective protocol header e.g ipv4
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            print("           {:17},      {:17} --> {}".format(ip_pkt.src, ip_pkt.dst, L4PROTO[ip_pkt.proto]))

#             Info: TCP Packet
            if ip_pkt.proto == 6:
                tcp_pkt = pkt.get_protocol(tcp.tcp)
                print("      SRC-PORT: {}, DST-PORT: {}, SEQ: {}, ACK: {}".format(tcp_pkt.src_port, tcp_pkt.dst_port, tcp_pkt.seq, tcp_pkt.ack))

#             Info: ARP Packet
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            print("  [ARP] SRC-MAC: {}, SRC-IP: {}; DST-MAC: {} DST-IP: {}".format(arp_pkt.src_mac, arp_pkt.src_ip, arp_pkt.dst_mac, arp_pkt.dst_ip))

    ## When a new switch connects to the controller
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        # install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                            ofproto.OFPCML_NO_BUFFER)]
        self.program_flow(dp, match, actions, 0, idle_timeout=0, hard_timeout=0)

        ## init (per-data path) variables
        #self.MAC_TO_PORT[dp.id] = {}
        self.pkt_count[dp.id] = 0

        ## some debug output
        print("")
        print("")
        print("/// Switch connected. ID: {}".format(dp.id))

    ## When a new packet comes in at the controller -- "PACKET-IN"
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        # all info is stored in the ev object, relevant fields are extracted
        msg = ev.msg
        datapath = msg.datapath
        data = msg.data
        pkt = packet.Packet(data)
        eth = pkt.get_protocol(ethernet.ethernet)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # get Datapath id to identify OpenFlow switches.
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # analyse the received packets using the packet library.
        pkt = packet.Packet(msg.data)
        ip = pkt.get_protocol(ipv4.ipv4)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        dst = eth_pkt.dst
        src = eth_pkt.src

        # get the received port number from the packet_in message
        in_port = msg.match["in_port"]

        # ignore LLDP Packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            # This is an ARP packet. It must be handled differently
            self.handle_arp(datapath, in_port, eth, data)
            return

        # This will discard packets which are not IPv4 packets
        if ip is None:
            return

        self.debug_output(datapath, pkt, in_port)

        # learn a mac address to avoid flood next time.
        self.mac_to_port[dpid][src] = in_port

        # if the destination mac address is already learned,
        # decide which port to output the packet, otherwise flood.
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        # action list will either flood traffic or send it to correct port
        # based on condition outlined above
        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time.
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.program_flow(datapath, match, actions, 1, idle_timeout=0, hard_timeout=0)

        # construct a packet_out message and send it.
        out = parser.OFPPacketOut(datapath=datapath,
                                    buffer_id=ofproto.OFP_NO_BUFFER,
                                    in_port=in_port, actions=actions,
                                    data=msg.data)
        datapath.send_msg(out)

        # if this is a new ip address then add it to dictionary and assign it a count of
        # zero for sent syn packets and zero for sent ack packets
        if not ip.src in self.packets_by_ip:
            self.packets_by_ip[ip.src] = [0, 0]

        # if this is a tcp packet then the total tcp count will increase by 1 and this information
        # is printed to screen
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            if ip.proto == 6:
                tcp_pkt = pkt.get_protocol(tcp.tcp)
                self.total_packets+=1
                print("TCP packet total : {}".format(self.total_packets))
                # if this is a syn packet then the syn counter is incremented by 1 and printed to screen
                if tcp_pkt.has_flags(tcp.TCP_SYN):
                    self.syn_counter += 1
                    # the number of sent syn packets for that ip address is incremented by 1 in
                    # the self.packets_by_ip list as well
                    self.packets_by_ip[ip.src][0] += 1
                    print("SYN total : {}".format(self.syn_counter))
                elif tcp_pkt.has_flags(tcp.TCP_ACK):
                    # similarly ack packets are counted and printed
                    self.ack_counter += 1
                    # and the ack packets sent are counted per ip address and incremented
                    self.packets_by_ip[ip.dst][1] += 1
                    print("ACK total : {}".format(self.ack_counter))

        # if the user has sent syn packets but not sent ack packets then a drop flow rule is created
        if self.packets_by_ip[ip.src][0] > 2 and self.packets_by_ip[ip.src][1] == 0 and ip.src not in self.trusted_users:
            # match rule will target the ip source - in this case a spoofed ip address.
            match = parser.OFPMatch(
                eth_type = ether_types.ETH_TYPE_IP,
                ipv4_src = ip.src
                )
            # the action is set to drop packets
            action = []
            # the flow rule is set with a high priority and an idle timeout of 10 seconds
            # if a legitmate ip address sends a syn packet it will be blocked. but after the idle timeout passes
            # that user may send data on the network
            self.program_flow(datapath, match, action, priority=200, idle_timeout=0, hard_timeout=0)

            # if the user has sent ten syn packets and ten ack packets they will be added to a trusted user list
            # this will hopefully make the application faster as there are fewer ip addresses to consider when
            # checking for ip addresses sending malicious traffic
        elif self.packets_by_ip[ip.src][0] > 10 and self.packets_by_ip[ip.src][1] > 10 and ip.src not in self.trusted_users:
            self.trusted_users.append(ip.src)

            # if a single ip address sends over 1000 syn packets they will be blocked for 60 seconds
            # this means any user on the system sending a high volume of traffic is restricted.
        elif self.packets_by_ip[ip.src][0] > 1000:
            match = parser.OFPMatch(
                eth_type = ether_types.ETH_TYPE_IP,
                ipv4_src = ip.src
                )
            action = []
            self.program_flow(datapath, match, action, priority=200, idle_timeout=60, hard_timeout=60)

        ## CODE BELOW IS AN ALTERNATE METHOD ##
        ## This is an incomplete approach. Just something experimented with in the late stages of the project ##

        #while self.syn_counter - self.ack_counter > 1000:
        #    if self.packets_by_ip[ip.src][0] > 0 and self.packets_by_ip[ip.src][1] == 0 and ip.src not in self.trusted_users:
            # match rule will target ip destination and tcp traffic with a SYN flag. This will cut off all SYN traffic to the
            # target ip address until hard timeout ends. This will however violate CIA triad of availability
        #        match = parser.OFPMatch(
        #        eth_type=0x0800,
        #        ip_proto=6,
        #        tcp_flags=0x002,
        #        ipv4_dst = ip.dst
        #        )
            # the action is set to drop packets
        #        self.program_flow(datapath, match, action, priority=200, idle_timeout=30, hard_timeout=30)
            # resetting the counters will help determine when the balance of syn - ack traffic normalizes
            # on the network and the attack has ended
        #        self.new_counter_1 = 0
        #        self.new_counter_2 = 0
        #        self.syn_counter = self.new_counter_1
        #        self.ack_counter = self.new_counter_2

        ## END OF ALTERNATE METHOD ##

        #print(self.packets_by_ip)
        #for key in self.packets_by_ip:
        #    print(key, '->', self.packets_by_ip[key])
        #print(self.trusted_users)

        # this will clear our list of ip addresses and syn/ack information after the list grows
        # too large. This will prevent the application from becoming slower as it has to search through
        # an ever growing list
        if len(self.packets_by_ip) > 10000:
            self.packets_by_ip.clear()

        #print(len(self.packets_by_ip))

    def handle_arp(self, datapath, in_port, eth, data):
        """ This method implements a simple mechanism to install
            forwarding rules for ARP packets. Packets that are
            not handled by any of these rules are flooded to
            nearby switches.
        """
        ofproto = datapath.ofproto

        dst = eth.dst
        src = eth.src

        match = parser.OFPMatch(
            eth_type = ether_types.ETH_TYPE_ARP,
            eth_dst = src
        )

        # Forwards ARP packets to directly connected
        # network nodes so we don't have to bother with subsequent
        # ARP packets anymore.
        self.program_flow(datapath, match, [parser.OFPActionOutput(in_port)],
            priority = 1, idle_timeout=0, hard_timeout=0)

        # Flood the received ARP message on all ports of the switch
        self.send_pkt(datapath, data, port = ofproto.OFPP_FLOOD)