# 3D Slicer Cast Interface Extension

<p align="center">
  <img src="CastInterface/docs/images/banner.png" alt="Cast Interface Banner" width="100%">
</p>


---

## Overview

Cast Interface is a 3D Slicer extension focused on desktop integration workflows for healthcare providers and researchers.


## Background

Cast is an offshoot of FHIRcast (<https://fhircast.hl7.org/>). FHIRcast is the standard replacing Epic’s file drop interface for integration with PACS and reporting systems. It provides a secure event messaging infrastructure using a hub with websocket subscriptions. The following animation shows distribution of a FHIRCast ImagingStudy-open event to all applications over low-latency websocket connections.
<figure>
  <p align="center">
    <img src="CastInterface/docs/images/imagingstudy-open-flow.svg"
         alt="ImagingStudy-open event flow: user selects an exam on the worklist, worklist publishes imagingstudy-open to the hub over HTTP POST, hub fans the event over WebSocket to Image Display, Reporting, and EHR, and each app updates its UI."
         width="100%">
  </p>

</figure>




You can get a feeling of websocket subscription integration with the vtk-js IO module cast interface example. Make sure to open a few viewers with different layouts and try the "Open scene views" button to try out cross-product multi-host display layouts:
[Open  worklist demo](https://slicerhub-azejffgnb7dve8es.canadaeast-01.azurewebsites.net/worklist-client/examples/CastClient/index.html)
[![Cast worklist client](CastInterface/docs/images/worklist-client.png)](https://slicerhub-azejffgnb7dve8es.canadaeast-01.azurewebsites.net/worklist-client/examples/CastClient.html)


Cast also has a context sharing strategy and hub architecture that diverges from FHIRcast, see description [here](CastInterface/docs/cast-description.md).



## Extension Features

The extension features a hub and two cast interfaces: one for connecting existing extensions like TotalSegmentator to the hub (Resource servers) and another one to connect the Slicer viewer (Image Display client) to the hub.


#### Hub:
The hub is the routing appliance that distributes the messages and handles the data transfer requests over the websocket connection to each client.

![hub](CastInterface/docs/images/hub-ui.png)

![hub portal](CastInterface/docs/images/hub-admin.png)

It can be used without the slicer extension by running the "cast_api.py" script. 

#### Resource servers:


Resource servers provide desktop integration of image processing services. This allow users to view AI results without having to send them to the archive first.

The resource server tab provides a visual description of how processing resources can be connected to the hub and made available to cast workflows.
Here for example, in the VolView client:
![Total Segmentator in VolView](CastInterface/docs/images/VolViewTotalSegmentator.png)


Resource servers subscribe to all user topics for status-request and dicom/nifti events. They send binary results back to the user through the hub.


Since these resources do not log in as a user, they need a resource server entry in the authorization server. This provides a client id and client secret.
For the cast extension hub, these must be configured in the environment variables of the hub for the resource to connect successfully.


![resource servers](CastInterface/docs/images/ResourceServerFeature.png)


This video shows VolView using the TotalSegmentator extension with the "Resource Server" setup. The video shows the binary transfer through the hub to 3D Slicer, pauses during the segmentation calculation and restarts just before the segmentation is sent to VolView.


<a href="https://www.youtube.com/watch?v=pHp5QpeH1JE">
  <img src="CastInterface/docs/images/video_thumbnail_resourceserver.png" alt="Resource server" width="900">
</a>



#### Image Display Client:
The image display client provides a PACS client type interface to the 3D Slicer viewer. Supported events include ImagingStudy-open, ImagingStudy-close, dicom-send, and status-request (embedded sceneview).


![image display client](CastInterface/docs/images/ImageDisplayClient.png)

### Simplified, secure deployment of medical imaging services


This architecture protects resource servers by eliminating direct inbound internet exposure entirely. No hostname is required and no changes to the networking environment are needed.


Each resource server establishes only outbound encrypted connections to the Cast Hub, which functions exclusively as a routing appliance. Because no inbound ports need to be opened on hospital or enterprise networks, the resource servers remain protected behind existing firewalls and are never directly reachable from the public internet.

It also simplifies providing resources in-house since the IT department only needs to add a hostname and rules for the hub. They do not have to touch their networking every time a new resource server is available for use. They only have to configure a shared key for it in their auth server.


For the hub, it provides a significantly reduced attack surface and minimizes operational security risk since it maintains no storage or database.
<p align="center">
  <img src="CastInterface/docs/images/deployment.png" alt="Cast Interface Banner" width="100%">
</p>


After installation, the resource servers outbound ports can also be locked down, allowing access to the hub and sites needed by the extension only.

In theory, the hub can be cloud deployed as a serverless application. In practice, many of those low-cost offerings do not support websocket services and a docker based offering is necessary like Azure WebApps or AWS Elastic Beanstalk.

For high availability deployment a hot standby configuration can be used. The "reset server" button in the hub admin portal allows testing workflow behavior during failover.

The hub provides a test mock auth endpoint that assigns a user when none is provided. For public web applications that do not need user authentication but want to use the resource servers, the mock endpoints provide the required functionality.

The hub also supports a “single-user” mode for stand-alone applications.

Since the resource servers are not on the internet, you will get shared keys for the auth server.
The hub can use domain name certificates.


## Installation

### Install from the 3D Slicer Extension Manager

1. Open **3D Slicer**
2. Open the **Extension Manager**
3. Search for **Cast Interface**
4. Click **Install**
5. Restart 3D Slicer

---

## License

MIT License

---

## Acknowledgements

* 3D Slicer community
* Open-source healthcare ecosystem
* Medical imaging interoperability initiatives

---

## Disclaimers

**Standards and trademarks**

DICOM® is the registered trademark of the National Electrical Manufacturers Association (NEMA) for its standards publications relating to digital imaging and communications in medicine. FHIR® and related HL7 marks are registered trademarks of Health Level Seven International (HL7). IHE® is a registered trademark of HIMSS. VolView® is a trademark of Kitware, Inc. OHIF® is a trademark of the Open Health Imaging Foundation. Imaging Data Commons® is a trademark of the National Cancer Institute.

The Cast Interface (including its hub, clients, and documentation) references ideas, workflows, and vocabulary drawn from these standards—such as DICOM objects and metadata, FHIR and FHIRcast-style context and events, and IHE actor roles (for example, Image Display and Evidence Creator)—and product names such as VolView, OHIF, and Imaging Data Commons solely to describe interoperability behavior.

**Cast Interface is not part of these standards.** It is not published by NEMA, HL7, or HIMSS, and is not an IHE Integration Profile, a FHIR implementation guide, or a DICOM conformance statement. Use of standard names and terms does not imply endorsement, certification, or official status. All other product and company names are trademarks of their respective owners.