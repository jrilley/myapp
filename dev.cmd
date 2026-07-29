@echo off
REM Запуск бекенду і фронтенду однією командою: .\dev.cmd
REM Обходить політику виконання PowerShell — .cmd їй не підпорядковується,
REM на відміну від npm.ps1.

REM Консоль Windows за замовчуванням у cp866/cp1251 і показує UTF-8 як
REM кракозябри. 65001 = UTF-8; діє лише в цьому вікні.
chcp 65001 >nul

node "%~dp0scripts\dev.mjs" %*
