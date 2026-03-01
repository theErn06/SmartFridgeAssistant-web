' File: run_hidden.vbs
' This script launches the Ollama server and the Python assistant sequentially, both hidden.

Set shell = CreateObject("WScript.Shell")

' 1. Start Ollama Server
' This command ensures the Ollama service starts up and prepares models.
' The '0' keeps the command window hidden.
shell.Run "cmd /c ollama serve", 0, false 

' 2. Wait for the Ollama server to initialize and load the 'jarvis' model.
' 5000 milliseconds = 5 seconds. Adjust this if you still get timeout errors on startup.
WScript.Sleep 5000 

' 3. Start the Python listener (Your main assistant script)
' The '0' keeps the command window hidden.
shell.Run "cmd /c python king.py", 0, true