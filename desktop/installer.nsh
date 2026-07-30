!ifdef BUILD_UNINSTALLER
  Var /GLOBAL KnoArborDeleteLocalData
!endif

!macro stopKnoArborInstalledProcesses RESULT
  System::Call 'Kernel32::SetEnvironmentVariable(t "KNOARBOR_INSTALL_APP_PATH", t "$INSTDIR\${APP_EXECUTABLE_FILENAME}") i .r0'
  System::Call 'Kernel32::SetEnvironmentVariable(t "KNOARBOR_INSTALL_SERVICE_PATH", t "$INSTDIR\resources\service\knoar-service.exe") i .r0'
  nsExec::ExecToLog `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$matchesTarget = { $$path = $$_.ExecutablePath; $$path -and ([String]::Equals($$path, $$env:KNOARBOR_INSTALL_SERVICE_PATH, [StringComparison]::OrdinalIgnoreCase) -or [String]::Equals($$path, $$env:KNOARBOR_INSTALL_APP_PATH, [StringComparison]::OrdinalIgnoreCase)) }; $$processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue | Where-Object $$matchesTarget); foreach ($$process in $$processes) { Stop-Process -Id $$process.ProcessId -Force -ErrorAction SilentlyContinue }; if ($$processes.Count -gt 0) { Start-Sleep -Milliseconds 500 }; $$remaining = @(Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue | Where-Object $$matchesTarget); if ($$remaining.Count -gt 0) { exit 1 }; exit 0"`
  Pop ${RESULT}
  System::Call 'Kernel32::SetEnvironmentVariable(t "KNOARBOR_INSTALL_APP_PATH", p 0) i .r0'
  System::Call 'Kernel32::SetEnvironmentVariable(t "KNOARBOR_INSTALL_SERVICE_PATH", p 0) i .r0'
!macroend

!macro customCheckAppRunning
  DetailPrint "Stopping the installed KnoArbor application and managed service..."
  !insertmacro stopKnoArborInstalledProcesses $R0
  ${If} $R0 != 0
    MessageBox MB_OK|MB_ICONSTOP "KnoArbor could not stop the installed application or its managed service. Close them and retry."
    Abort
  ${EndIf}
!macroend

!macro customUnInit
  StrCpy $KnoArborDeleteLocalData "0"
  ${IfNot} ${isUpdated}
    ClearErrors
    ${GetParameters} $R0
    ${GetOptions} $R0 "/S" $R1
    ${If} ${Errors}
      MessageBox MB_YESNO|MB_ICONQUESTION "Remove local KnoArbor data as well? This includes configuration, chats, internal vaults, logs, and caches. External vaults are never removed.$\r$\n$\r$\n是否同时删除 KnoArbor 本机数据（配置、会话、内部知识库、日志和缓存）？外部知识库不会被删除。" /SD IDNO IDNO +2
      StrCpy $KnoArborDeleteLocalData "1"
    ${EndIf}
  ${EndIf}
!macroend

!macro customUnInstall
  DetailPrint "Stopping the KnoArbor managed service..."
  !insertmacro stopKnoArborInstalledProcesses $R0
  ${If} $R0 != 0
    MessageBox MB_OK|MB_ICONSTOP "KnoArbor could not stop its managed service. Close the application and retry uninstalling."
    Abort
  ${EndIf}
  ${If} $KnoArborDeleteLocalData == "1"
    DetailPrint "Removing local KnoArbor product data..."
    RMDir /r "$LOCALAPPDATA\KnoArbor"
  ${EndIf}
!macroend
