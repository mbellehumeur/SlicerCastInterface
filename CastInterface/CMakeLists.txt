#-----------------------------------------------------------------------------
set(MODULE_NAME CastInterface)
set(EXTENSION_HOMEPAGE "https://github.com/mbellehumeur/SlicerCastInterface/")
set(EXTENSION_CATEGORY "Ultrasound")
set(EXTENSION_CONTRIBUTORS "Martin Bellehumeur")
set(EXTENSION_DESCRIPTION "Desktop Integration for Healthcare Providers and Researchers.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/SlicerCastInterface/main/CastInterface/docs/images/CastInterfaceExtensionLogo.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/SlicerCastInterface/main/CastInterface/docs/images/hub-admin.png")

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  CastInterface.py
  Lib/CastHub.py
  Lib/CastImageDisplayClient.py
  Lib/CastResourceServers.py
  Lib/cast_client.py
  Lib/cast_provider_runtime.py
  Lib/image_display_client_handler.py
  Lib/image_display_client_hub.py
  Lib/image_display_client_load.py
  Lib/image_display_client_requests.py
  Lib/build_sceneview_response.py
  Lib/imaging_study_context.py
  Lib/resource_server_hub.py
  Lib/__init__.py
  )

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES Resources
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)

  slicer_add_python_unittest(SCRIPT CastInterface.py)

  add_subdirectory(Testing)
endif()
