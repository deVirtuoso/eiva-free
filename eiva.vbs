' EIVA (Free), started with no console window at all.
'
' eiva.cmd shows one for a moment before it closes. This does the same job
' through the Windows scripting host, which has no console to give. Use
' whichever you prefer, and pin this one to the taskbar to have it always to
' hand. First run hands over to eiva.cmd so setup can be read.

Option Explicit
Dim shell, fso, here, python, script, ready
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
python = here & "\.venv\Scripts\pythonw.exe"
script = here & "\eiva.py"
shell.CurrentDirectory = here
' Being there is not the same as working: the virtual environment holds an
' absolute path to the Python it was built from, and that Python can be
' upgraded or uninstalled out from under it. Ask it to run - 0 = no window,
' True = wait for the answer - and hand over to eiva.cmd, which repairs it,
' if it cannot.
ready = False
If fso.FileExists(python) Then
    ready = (shell.Run("""" & python & """ -c pass", 0, True) = 0)
End If

If Not ready Then
    shell.Run """" & here & "\eiva.cmd""", 1, False
Else
    shell.Run """" & python & """ """ & script & """", 0, False
End If
