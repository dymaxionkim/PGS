import customtkinter
from customtkinter import filedialog
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from GPG import GPG
from PGS import PGS

# Planetary Gear Sizing Class
P1 = PGS()

# PGS Spec
P1.TYPE = 3 # 0=Simple, 1=Wolfrom(diff=1), 2=Wolfrom(diff=0.5), 3=Wolfrom(diff=2)
P1.m = 0.5 # Common Module
P1.Np = 4  # Planets Number (it must be even number)
P1.Zr2_MultipleNp = 15
P1.Zs1_MultipleNp = 8

# Gear Class
Gs1 = GPG()
Gp1 = GPG()
Gr1 = GPG()
if P1.TYPE!=0:
    Gs2 = GPG()
    Gp2 = GPG()
    Gr2 = GPG()

# PGS Calc
P1.Calc()
P1.Output()
P1.Checks()

# Gear Spec
Gs1.M = P1.m1
Gs1.Z = P1.Zs1
Gp1.M = P1.m1
Gp1.Z = P1.Zp1
Gp1.Y_0 = P1.Dc/2.0
Gr1.M = P1.m1
Gr1.Z = P1.Zr1
if P1.TYPE!=0:
    Gs2.M = P1.m2
    Gs2.Z = P1.Zs2
    Gp2.M = P1.m2
    Gp2.Z = P1.Zp2
    Gp2.Y_0 = P1.Dc/2.0
    Gr2.M = P1.m2
    Gr2.Z = P1.Zr2

# Gear Calc
Gs1.Calc()
Gp1.Calc()
Gr1.Calc()
if P1.TYPE!=0:
    Gs2.Calc()
    Gp2.Calc()
    Gr2.Calc()

# Plot Gs1
Sun_Angle = 0.0
if Gp1.Z%2==0:
    Sun_Angle = (2*np.pi/Gs1.Z)/2
Gs1_X = np.cos(Sun_Angle)*Gs1.X8 - np.sin(Sun_Angle)*Gs1.Y8
Gs1_Y = np.sin(Sun_Angle)*Gs1.X8 + np.cos(Sun_Angle)*Gs1.Y8
plt.plot(Gs1_X,Gs1_Y,'blue')
plt.plot(Gs1.Xp,Gs1.Yp,'r:')

# Plot Gp1
Gp1_Array_Angle = 2*np.pi/P1.Np
for i in range(0,P1.Np):
    Gp1_Array_X = np.cos(Gp1_Array_Angle*i)*Gp1.X8 - np.sin(Gp1_Array_Angle*i)*Gp1.Y8
    Gp1_Array_Y = np.sin(Gp1_Array_Angle*i)*Gp1.X8 + np.cos(Gp1_Array_Angle*i)*Gp1.Y8
    Gp1_Array_Xp = np.cos(Gp1_Array_Angle*i)*Gp1.Xp - np.sin(Gp1_Array_Angle*i)*Gp1.Yp
    Gp1_Array_Yp = np.sin(Gp1_Array_Angle*i)*Gp1.Xp + np.cos(Gp1_Array_Angle*i)*Gp1.Yp
    plt.plot(Gp1_Array_X,Gp1_Array_Y,'green')
    plt.plot(Gp1_Array_Xp,Gp1_Array_Yp,'r:')

# Plot Gr1
plt.plot(Gr1.X8,Gr1.Y8,'black')
plt.plot(Gr1.Xp,Gr1.Yp,'r:')

# Plot Gs2
if P1.TYPE!=0:
    Sun_Angle = 0.0
    if Gp2.Z%2==0:
        Sun_Angle = (2*np.pi/Gs2.Z)/2
    Gs2_X = np.cos(Sun_Angle)*Gs2.X8 - np.sin(Sun_Angle)*Gs2.Y8
    Gs2_Y = np.sin(Sun_Angle)*Gs2.X8 + np.cos(Sun_Angle)*Gs2.Y8
    plt.plot(Gs2_X,Gs2_Y,'blue')
    plt.plot(Gs2.Xp,Gs2.Yp,'r:')

# Plot Gp2
if P1.TYPE!=0:
    Gp2_Array_Angle = 2*np.pi/P1.Np
    for i in range(0,P1.Np):
        Gp2_Array_X = np.cos(Gp2_Array_Angle*i)*Gp2.X8 - np.sin(Gp2_Array_Angle*i)*Gp2.Y8
        Gp2_Array_Y = np.sin(Gp2_Array_Angle*i)*Gp2.X8 + np.cos(Gp2_Array_Angle*i)*Gp2.Y8
        Gp2_Array_Xp = np.cos(Gp2_Array_Angle*i)*Gp2.Xp - np.sin(Gp2_Array_Angle*i)*Gp2.Yp
        Gp2_Array_Yp = np.sin(Gp2_Array_Angle*i)*Gp2.Xp + np.cos(Gp2_Array_Angle*i)*Gp2.Yp
        plt.plot(Gp2_Array_X,Gp2_Array_Y,'green')
        plt.plot(Gp2_Array_Xp,Gp2_Array_Yp,'r:')

# Plot Gr2
if P1.TYPE!=0:
    plt.plot(Gr2.X8,Gr2.Y8,'black')
    plt.plot(Gr2.Xp,Gr2.Yp,'r:')

# Plot show
plt.axis("equal")
plt.grid("on")
plt.show()



def button_run_callback():
    global label_image
    print("button_run pressed")
    read_parameters()
    os.makedirs(WorkingDirectory, exist_ok=True)
    FGPG2_PLOT(m,z,alpha,x,b,a,d,c,e,x_0,y_0,seg_circle,seg_involute,seg_edge_r,seg_root_r,seg_outer,seg_root,scale)
    save_parameters()
    Result = os.path.join(WorkingDirectory, f'Result1.png')
    image_result = customtkinter.CTkImage(light_image=Image.open(Result), size=(500,500))
    label_image = customtkinter.CTkLabel(app, text="", image=image_result)
    label_image.grid(row=1, column=3, padx=PADX, pady=PADY, rowspan=16, columnspan=4)
    label_text.configure(text='Finished geneating')

def button_exit_callback():
    print("button_exit pressed")
    exit()

################
# GUI
customtkinter.set_default_color_theme("green")
app = customtkinter.CTk()
app.title("PGS with customtkinter")
app.geometry("950x650")
app.resizable(width=False, height=False)
font16 = customtkinter.CTkFont(size=16)
if ( sys.platform.startswith('win')): app.iconbitmap('PGS.ico')
# Gap between pads in customtkinter
PADX = 1
PADY = 1

# Subject
label_P1 = customtkinter.CTkLabel(app, text="# Planetary System", fg_color="transparent", compound="right", font=font16)
label_P1.grid(row=0, column=0, padx=PADX, pady=PADY, sticky="w")

# Type, TYPE
label_TYPE1 = customtkinter.CTkLabel(app, text="Type, TYPE = ", fg_color="transparent", compound="right")
label_TYPE1.grid(row=1, column=0, padx=PADX, pady=PADY, sticky="e")
entry_TYPE = customtkinter.CTkEntry(app, placeholder_text="1")
entry_TYPE.grid(row=1, column=1, padx=PADX, pady=PADY)
label_TYPE2 = customtkinter.CTkLabel(app, text="0=Simple, 1=Wolfrom(diff=1), 2=Wolfrom(diff=0.5), 3=Wolfrom(diff=2)", fg_color="transparent", compound="left")
label_TYPE2.grid(row=1, column=2, padx=PADX, pady=PADY, sticky="w")

# Module, m
label_m1 = customtkinter.CTkLabel(app, text="Module, m = ", fg_color="transparent", compound="right")
label_m1.grid(row=2, column=0, padx=PADX, pady=PADY, sticky="e")
entry_m = customtkinter.CTkEntry(app, placeholder_text="1.0")
entry_m.grid(row=2, column=1, padx=PADX, pady=PADY)
label_m2 = customtkinter.CTkLabel(app, text="[mm] > 0", fg_color="transparent", compound="left")
label_m2.grid(row=2, column=2, padx=PADX, pady=PADY, sticky="w")

# Planets Number, Np
label_m1 = customtkinter.CTkLabel(app, text="Planets Number, Np = ", fg_color="transparent", compound="right")
label_m1.grid(row=3, column=0, padx=PADX, pady=PADY, sticky="e")
entry_m = customtkinter.CTkEntry(app, placeholder_text="4")
entry_m.grid(row=3, column=1, padx=PADX, pady=PADY)
label_m2 = customtkinter.CTkLabel(app, text="[ea] > 2", fg_color="transparent", compound="left")
label_m2.grid(row=3, column=2, padx=PADX, pady=PADY, sticky="w")

# Zr2/Np
label_m1 = customtkinter.CTkLabel(app, text="Zr2*Np = ", fg_color="transparent", compound="right")
label_m1.grid(row=4, column=0, padx=PADX, pady=PADY, sticky="e")
entry_m = customtkinter.CTkEntry(app, placeholder_text="15")
entry_m.grid(row=4, column=1, padx=PADX, pady=PADY)
label_m2 = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label_m2.grid(row=4, column=2, padx=PADX, pady=PADY, sticky="w")

# Zs1/Np
label_m1 = customtkinter.CTkLabel(app, text="Zs1*Np = ", fg_color="transparent", compound="right")
label_m1.grid(row=5, column=0, padx=PADX, pady=PADY, sticky="e")
entry_m = customtkinter.CTkEntry(app, placeholder_text="8")
entry_m.grid(row=5, column=1, padx=PADX, pady=PADY)
label_m2 = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label_m2.grid(row=5, column=2, padx=PADX, pady=PADY, sticky="w")

# Button Run
button_run = customtkinter.CTkButton(app, text="Run", command=button_run_callback, width=50)
button_run.grid(row=6, column=0, padx=PADX, pady=PADY, sticky="e")

# Button exit
button_exit = customtkinter.CTkButton(app, text="Exit", command=button_exit_callback, width=50)
button_exit.grid(row=6, column=2, padx=PADX, pady=PADY, sticky="w")

app.mainloop()
