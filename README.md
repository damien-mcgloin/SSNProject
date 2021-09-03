# Mitigating a SYN flood DDoS attack in a software defined network 

### (CSC 7078) Damien McGloin 40000631 

# Gitlab Repository

1. Demonstration Video 
    - presentation.pptx (Video file size was too big for storing on gitlab so only the ppt used is located here)[click here](Demonstration_Video/Presentation.pptx)
2. Development Timeline
    - timeline.md (file containing screenshots from trello board outlining project timeline)[click here](Development_Timeline/timeline.md)
3. Images
    - Functional_Testing_Images [click here](Images/Functional_Testing_Images)
    - Non_Functional_Testing_Images [click here](Images/Non_Functional_Testing_Images)
4. Previous Application Versions
    - project_v_1.py (this version was worked on from week 3-4)[click here](Previous_Application_Versions/project_v_1)
    - project_v_2.py (this version was worked on from week 4-5)[click here](Previous_Application_Versions/project_v_2)
    - project_v_3.py (this version was worked on from week 5-6)[click here](Previous_Application_Versions/project_v_3)
5. Project Proposal
    - ProjectSummary_40000631_DamienMcGloin.pdf (the proposal submitted in week 2 - very different from the final application version)[click here](Project Proposal/ProjectSummary_40000631_DamienMcGloin.pdf)
6. SDN Application
    - project.py (the python application created to defend against a SYN flood ddos attack)[click here](SDN_Application/project.py)
    - projectscenario.yaml (the scenario created containing host names, links, ip addresses etc.)[click here](SDN_Application/projectscenario.yaml)
    - projecttask.yaml (a file outlining the task - mitigating a SYN flood ddos attack)[click here](SDN_Application/projecttask.yaml)
7. Testing
    - Test_Plan.md (a file providing an overview of testing - functional and non functional including results e.g pass or fail)[click here](Testing/Test_Plan.md)
    - Results.md (a file providing a deeper look at testing - this includes test evidence in the form of screenshots)[click here](Testing/Results.md)

# Objective 

To detect and mitigate a SYN flood DDoS attack within a virtual network

# Tools used to implement the project 

- SDN cockpit. 
- The hping3 tool will be used for generating traffic both malicious and otherwise. 
- The mininet virtual network emulator will be used within SDN cockpit to configure a network topology. 
- A ryu openflow controller (v1.3) will be used to implement the solution for monitoring and preventing the attack. 
- Wireshark will be used for highlighting the difference between legitimate and malicious users. 
- Xterm will be used to emulate terminal windows for various hosts.
- iPerf will be used for measuring bandwidth on the network.

# Network Topology Diagram

<div align="center">![Network Topology Diagram](../Images/Network_Topology_Diagram.png)</div>
<div align="center">Image 1 : Network Topology Diagram</div><br/>


This diagram showcases the topology used for the video demonstration and is the same as the topology present in
projectscenario.yaml which can be found in the SDN Application directory.
As shown above, two hosts will be used to demonstrate normal users on the network. Host 3 will run a http server and will serve as the target.
Hosts 4 - 8 are attackers and each will flood the attack target with syn packets. This will showcase the benefits and the
limitations of the approach used for this project. The diagram above is based on one shown in a research paper assessing techniques for
mitigating slow DDoS attacks [1].

# Requirements 

1. First, the creation of an application which can correctly identify a SYN flood attack. 
A key concern is differentiating between normal tcp traffic and users with malicious intent who violate the three way handshake.
2. Preserving availability is also of great importance as DDoS attacks typically target this element of the CIA triad. The application
aims to ensure that data can be transmitted on the network by legitimate users even while an attack is being blocked.
3. A simple network topology can be employed with a switch, a host representing a web server (the attack target), two hosts representing normal 
traffic and five hosts representing the attacker. 
 

# An overview of my application

1. First, my application uses a switching hub based on the one outlined in the ryu documentation found here 
[https://osrg.github.io/ryu-book/en/html/switching_hub.html]
This serves three functions.
    - It learns the MAC address of the host connected to a port and retains it in the MAC address table.
    - If a host has already been learned, transfers them to the port connected to the host.
    - When receiving packets addressed to an unknown host, it performs flooding.
2. Second, my application implements a traffic monitor based on the one outlined in the ryu documentation found here
[https://osrg.github.io/ryu-book/en/html/traffic_monitor.html]
This was adjusted slightly to also record duration in seconds. The number of transmitted packets and the duration are stored in a list every ten seconds.
This serves three functions.
    - It provides general information about the flow of traffic on the network.
    - It allows for the detection of a recent spike in traffic.
    - After a spike is detected traffic can then be redirected.
3. Third, after a high volume of traffic has been detected traffic is redirected to the controller.
This will add more latency but will allow for a response if a SYN flood attack is currently happening.
4. Fourth, ip addresses are recorded in a list along with the number of SYN packets they have sent and ACK packets they have received.
5. Fifth, after sending a SYN packet the user will be temporarily blocked by a drop flow rule. If they have also received an ack packet they will be able to
send traffic once the idle timeout on this drop rule expires.
6. If a user has sent and received a number of SYN and ACK packets they will be added to a trusted user list. They will no longer be challenged
unless they send a high volume of SYN packets

# Differentiating between a SYN flood and normal traffic

A typical TCP handshake can be seen in the image below. This screenshot was 
captured after creating a http server on a host running on the mininet virtual 
environment.

<div align="center">![TCP handshake](../Images/TCP_handshake.png)</div>
<div align="center">Image 2 : TCP handshake</div><br/>  

However, without using more advanced traffic generation methods the typical 
exchange after sending a SYN packet from one host to another within the mininet 
virtual environment can be seen below.

<div align="center">![SYN ACK Response](../Images/SYN_ACK_Response.png)</div>
<div align="center">Image 3 : Typical TCP Exchange Between Hosts</div><br/>  

In this example we can see a SYN, SYN ACK, RST ACK exchange. Therefore, differentiating between a SYN flood 
attack will be based on examining the ratio of SYN to ACK packets sent and received by hosts on the network. 
Spoofing an IP address will prevent a SYN ACK packet from reaching a user. Based on this,
it can be assumed that if a user is unable to receive a SYN ACK packet they are generating attack traffic. This 
is a simple approach to detection. It should be noted there are more advanced and more accurate methods of detection
such as comparing the SYN to FIN ratio. However, based on the SYN ACK interaction shown above this wouldn't be
effective here.

# Evaluation 

A test plan can be found in the testing folder. This outlines the tests run to ensure the application functions as intended.
Test evidence will primarily take the form of screenshots and will focus on things such as:

- Messages on the ryu display (this may for example indicate the controller is no longer being flooded after a drop flow rule was added).
- Round trip time which may be displayed in xterm windows.
- Bandwidth recorded using iPerf in xterm windows.
- Flow rules displaying information such as what was matched on and how many packets were dropped vs how many were sent.
- Graphs indicating the effectiveness of the application when there are additional hosts added.

The findings based on this evidence will be outlined below.  

# Functional Test Evaluation

- In terms of functionality the application performs as it was designed to. 
- It correctly monitors the network, detects high volumes of traffic sent within a short span of time, redirects 
TCP traffic to the controller and then collects data on each IP address.
- After assessing the ip addresses block rules are put in place for any users considered to be malicious.
- Testing repeatedly has shown that the time between the traffic monitor redirecting traffic can vary though based on the imprecise method
used to detect a spike in traffic within a short period of time.  
- The application's ability to block users becomes less effective as the number of hosts launching attack traffic increases.

# Non Functional Test Evaluation

- As shown through testing the effectiveness of the application depends heavily on two factors.
    1. The speed of the packets sent by an attacker
    2. The number of hosts attacking the system
- Sending packets at 100 per second led to a generally small percentage not being dropped
- The highest in this instance was 1.67% of the total packets sent
- Using the flood mode of the hping3 tool the drop rate became generally higher but this was not consistent throughout testing
- The highest drop rate was 17.78% when six hosts were attacking but with seven hosts attacking this was much lower. Only 3.84%
- This suggests the application can not reliably block high speed malicious traffic
- It also must be noted that during test 4.4, in which seven hosts launched a SYN flood attack against one target, the application was unable to create 
block rules for all seven attackers and a large amount of malicious traffic was not dropped as a result.
- Later in test 4.9 the application succeeded in blocking seven attackers. This failing may have been an anomaly but further indicates the
limitations of the application.
- It is likely that generating too many flow rules would severely limit the effectiveness of the solution
- The duration of the attack must be noted as well.
- Using the hping3 attack tool's flood mode this duration ranged from a low of 38 seconds with one attacker to a high of 675 seconds with six attackers.
- The time to set up the attack should also be considered which increases based on the number of hosts launching an attack.
- However, this does highlight that the more attackers there are on the system the slower it is at stopping an attack.

# Conclusion

- While the application has been shown to successfully block traffic from up to seven hosts there are serious limitations as well.
- The possibility of too many flow rules overwhelming the system, the number of packets not being blocked when there are multiple attackers and
and the increasing time period in which the controller must process packets which were not blocked.
- These failings of the application highlight the benefits of a second approach in which the application does not target the attacker but instead
targets the destination.
- Blocking SYN traffic from reaching the destination would affect availability and in a sense does the attacker's job for them.
- However, the advantages may outweigh the disadvantages.
- With a longer timeline for this project the next step would be creating this kind of alternate solution.

# References

[1] T. Lukaseder, S. Ghosh, F. Kargl, "Mitigation of Flooding and Slow DDoS Attacks in a Software-Defined Network" 2018. 
Available: Research Gate, https://www.researchgate.net. [Accessed: July 11, 2021]  
[2] D. Ngo, C. Pham-Quoc, T. N. Thinh, "An Efficient High-Throughput and Low-Latency SYN Flood Defender for High-Speed Networks" 2018.
Available: Research Gate, https://www.researchgate.net. [Accessed: July 14, 2021]  
[3] K. Phemius, M. Bouet, "Monitoring latency with OpenFlow" 2013. 
Available: IEEE, https://ieeexplore.ieee.org/Xplore/home.jsp. [Accessed July 11, 2021]  
[4] H. Wang, D. Zhang, K. G. Shin, "Detecting SYN Flooding Attacks" 2002.
Available: IEEE, https://ieeexplore.ieee.org/Xplore/home.jsp. [Accessed July 12, 2021]  
[5] S. Wang, Q. Sun, H. Zou, F. Yang, "Detecting SYN flooding attacks based on traffic prediction" 2012.
Available: Wiley Online Library, https://onlinelibrary.wiley.com/. [Accessed July 11, 2021]  
[6] Cloudflare, "SYN flood attack" [Online]. Available: https://www.cloudflare.com/en-gb/learning/ddos/syn-flood-ddos-attack/
[Accessed July 12 2021]  
[7] Ryubook 1.0 documentation, "RYU SDN Framework" [Online]. Available: https://osrg.github.io/ryu-book/en/html/
[Accessed July 10 2021]  
[8] RYU SDN Framework, "Using Openflow 1.3" [Online]. Available: https://osrg.github.io/ryu-book/en/Ryubook.pdf
[Accessed July 10, 2021]  
[9] Y. Zhou, K. Chen, J. Zhang, J. Leng, Y. Tang, "Exploiting the Vulnerability of Flow Table Overflow in Software-Defined Network:
Attack, Model, Evaluation, and Defense" 2018. Available: Research Gate, https://www.researchgate.net. [Accessed: July 24, 2021]  
[10] imperva, "TCP SYN Flood" [Online]. Available: https://www.imperva.com/learn/ddos/syn-flood/
[Accessed July 16 2021]  
[11] M. Bellaiche, J. C. Gregoire, "SYN flooding attack detection by TCP handshake anomalies" 2011.
Available: Wiley Online Library, https://onlinelibrary.wiley.com/. [Accessed July 21, 2021]  
