@echo off
rem Double-click this to install Company Brain on your server. It starts
rem install-from-windows.ps1, which must be in the same folder. See docs/install/windows.md.
rem -ExecutionPolicy Bypass applies to this one run only and changes no setting on this computer.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-from-windows.ps1"
