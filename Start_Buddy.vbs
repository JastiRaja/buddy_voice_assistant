Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

pythonwExe = scriptDir & "\venv\Scripts\pythonw.exe"
mainPy = scriptDir & "\main.py"

If fso.FileExists(pythonwExe) Then
    WshShell.Run """" & pythonwExe & """ """ & mainPy & """", 0, False
Else
    WshShell.Run "cmd /c run.bat", 0, False
End If
