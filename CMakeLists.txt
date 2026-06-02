cmake_minimum_required(VERSION 3.20.6...3.22.6 FATAL_ERROR)

project(pw45)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/mbellehumeur/SlicerCastInterface")
set(EXTENSION_CONTRIBUTORS "Martin Bellehumeur (Radical Imaging)")
set(EXTENSION_DESCRIPTION "This is a cast implementation where 3D slicer is a server process getting dicom-send events from all users connected to the hub and sending back a dicom-send to the user that sent the image.")
set(EXTENSION_ICONURL "https://github.com/mbellehumeur/SlicerCastInterface/blob/main/docs/images/CastInterfaceExtensionLogo.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/pw45/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CastInterface)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
