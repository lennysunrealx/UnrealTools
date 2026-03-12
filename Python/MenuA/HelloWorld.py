import unreal

unreal.log("Hello World")

unreal.EditorDialog.show_message(
    "QuickPy",
    "Hello World",
    unreal.AppMsgType.OK
)