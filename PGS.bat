REM Python Environment
REM set root=%USERPROFILE%\anaconda3
REM set root=%ProgramData%\anaconda3
set root=%USERPROFILE%\scoop\apps\miniconda3\current

call %root%\Scripts\activate.bat %root%
REM call conda env list
call conda activate base

REM Start App
call cd /d D:\github\PGS\
call python design.py

REM pause
exit