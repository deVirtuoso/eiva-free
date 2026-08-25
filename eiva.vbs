' EIVA (Free), started with no console window at all.
'
' eiva.cmd shows one for a moment before it closes. This does the same job
' through the Windows scripting host, which has no console to give. Use
' whichever you prefer, and pin this one to the taskbar to have it always to
' hand. First run hands over to eiva.cmd so setup can be read.

Option Explicit
Dim shell, fso, here, python, script
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
python = here & "\.venv\Scripts\pythonw.exe"
script = here & "\eiva.py"
shell.CurrentDirectory = here
If Not fso.FileExists(python) Then
    shell.Run """" & here & "\eiva.cmd""", 1, False
Else
    shell.Run """" & python & """ """ & script & """", 0, False
End If
