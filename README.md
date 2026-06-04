# 3D Slicer Cast Interface Extension

<p align="center">
  <img src="CastInterface/docs/images/banner.png" alt="Cast Interface Banner" width="100%">
</p>


---

## Overview

Cast Interface is a 3D Slicer extension focused on desktop integration workflows for healthcare providers and researchers.


## Background

Cast is an offshoot of FHIRcast (<https://fhircast.hl7.org/>). FHIRcast is the standard replacing Epic’s file drop interface for integration with PACS and reporting systems. It provides a secure event messaging infrastructure using a hub with websocket subscriptions.  The following animation shows distribution of a FHIRCast ImagingStudy-open event to all applications over low-latency websocket connections. 
<figure>
  <p align="center">
    <img src="CastInterface/docs/images/imagingstudy-open-flow.svg"
         alt="ImagingStudy-open event flow: user selects an exam on the worklist, worklist publishes imagingstudy-open to the hub over HTTP POST, hub fans the event over WebSocket to Image Display, Reporting, and EHR, and each app updates its UI."
         width="100%">
  </p>

</figure>




You can get a feeling for Cast with the vtk-js IO module cast interface example:
**[Open live worklist demo](https://slicerhub-azejffgnb7dve8es.canadaeast-01.azurewebsites.net/worklist-client/examples/CastClient/index.html)**
[![Cast worklist client](CastInterface/docs/images/worklist-client.png)](https://slicerhub-azejffgnb7dve8es.canadaeast-01.azurewebsites.net/worklist-client/examples/CastClient/index.html)


Cast also has a context sharing strategy and hub architecture that diverges from FHIRcast ([full Cast description](CastInterface/docs/cast-description.md)).



## Extension Features

The extension features a hub and two cast interfaces:  one for connecting existing extensions like TotalSegmentator to the hub (Resource servers) and another one connect the  slicer viewer (Image Display client)  to the hub.


#### Hub: 
The hub is the server that distributes the messages and handles the data transfer requests over the websocket connection to each client.

![hub](CastInterface/docs/images/hub-ui.png)

![hub portal](CastInterface/docs/images/hub-admin.png)

Online example:  
https://slicerhub-azejffgnb7dve8es.canadaeast-01.azurewebsites.net/api/hub/admin

#### Resource servers: 
The resource server tab provides a way for other 3D slicer extensions to connect to the hub and provide their resource to the users.  Resource servers subscribe to all user topics for dicom/nifti events and send back results to the user through the hub. Developers can setup a hub in the cloud and connect the extension running on their local machine to the cloud.  The instance in their dev environment is therefore available to their test parters in the cloud without having to deploy their code.


![resource servers](CastInterface/docs/images/ResourceServerFeature.png)


This video shows VolView using the TotalSegmentator extension with the "Resource Server" setup. The video shows the binary transfer through the hub to 3D Slicer, pauses during the segmentation calculation and restarts just before the segmentation is sent to VolView.


<a href="https://www.youtube.com/watch?v=pHp5QpeH1JE">
  <img src="CastInterface/docs/images/video_thumbnail_resourceserver.png" alt="Resource server" width="900">
</a>



#### Image Display Client: 
The image display client provide a PACS client type interface to the 3D slicer viewer. Supported events should be ImagingStudy-open, Imaging-Study-close, dicom-send and request for sceneview.


![image display client](CastInterface/docs/images/ImageDisplayClient.png)

### Security Benefits for cloud deployment of 3D Slicer extensions 

This architecture protects resource servers by eliminating direct inbound internet exposure entirely.

With resource servers, developers can connect  the code running on their machine to their cloud hub instance. The instance in their dev environment is therefore available to their remote parters without having to deploy their code to a cloud server.  


Each resource server establishes only **outbound encrypted connections** to the Cast Hub, which functions exclusively as a  **routing  appliance**. Because no inbound ports need to be opened on hospital or enterprise networks, the resource servers remain protected behind existing firewalls and are never directly reachable from the public internet.

It also simplifies providing resources in-house  since the IT department only needs to add a hostname and rules for the hub.  They do not have to touch their networking every time a new resource server is available for use.  They only have to configure a shared key for it in their auth server.


For the hub, it provides a significantly reduced attack surface and minimizes operational security risk since it maintains no storage or database. 
<p align="center">
  <img src="CastInterface/docs/images/deployment.png" alt="Cast Interface Banner" width="100%">
</p>


After installation, the resource servers outbound ports can also be locked down, allowing access to the hub and sites needed by the extension only.

In theory, the hub can be cloud deployed as a serverless application.  In practice, many of those low cost offerings do not support websocket services and a docker based offering is necessary like  Azure WebApps or AWS elastic beanstalk.  

For high availibity deployment a  hot stand-by configuration can be used.  The "reset server" button in the hub admin portal allows testing workflow behavior during failover.

The hub provides a test mock auth endpoint that assigns a user  when none is provided. For public web applications that do not need user authentication but want to use the resource servers, the mock endpoints provide the required functionality.  

The hub also supports a “single-user” mode  for stand-alone applications.

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
