REM Python Environment

REM path
set root=%USERPROFILE%\miniforge3
call %root%\Scripts\activate.bat %root%
call conda activate base

REM Start App
call cd /d D:\github\PGS\
call python design.py

REM pause
exit