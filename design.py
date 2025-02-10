import customtkinter
from customtkinter import filedialog
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import pandas
from GPG import GPG
from PGS import PGS

################
# Functions

def init_parameters():
    entry_TYPE.insert(0,1)
    entry_m.insert(0,0.5)
    entry_Np.insert(0,3)
    entry_Zr2overNp.insert(0,20)
    entry_Zs1overNp.insert(0,7)
    entry_Gs1X.insert(0,0.2)
    entry_Gs2X.insert(0,-0.05)
    entry_B.insert(0,0.04)
    entry_A.insert(0,1.0)
    entry_D.insert(0,1.25)
    entry_alpha.insert(0,20)
    entry_C.insert(0,0.2)
    entry_E.insert(0,0.1)
    entry_PlotOption.insert(0,3)

def read_parameters():
    P1.TYPE = int(entry_TYPE.get())
    P1.m = float(entry_m.get())
    P1.Np = int(entry_Np.get())
    P1.Zr2_MultipleNp = int(entry_Zr2overNp.get())
    P1.Zs1_MultipleNp = int(entry_Zs1overNp.get())
    P1.alpha = float(entry_alpha.get())
    ## G1
    Gs1.M = float(entry_m.get())
    Gp1.M = float(entry_m.get())
    Gr1.M = float(entry_m.get())
    Gs1.X = float(entry_Gs1X.get())
    Gs1.B = float(entry_B.get())
    Gp1.B = float(entry_B.get())
    Gr1.B = float(entry_B.get())
    Gs1.A = float(entry_A.get())
    Gp1.A = float(entry_A.get())
    Gr1.A = float(entry_A.get())
    Gs1.D = float(entry_D.get())
    Gp1.D = float(entry_D.get())
    Gr1.D = float(entry_D.get())
    Gs1.ALPHA = float(entry_alpha.get())
    Gp1.ALPHA = float(entry_alpha.get())
    Gr1.ALPHA = float(entry_alpha.get())
    Gs1.C = float(entry_C.get())
    Gp1.C = float(entry_C.get())
    Gr1.C = float(entry_C.get())
    Gs1.E = float(entry_E.get())
    Gp1.E = float(entry_E.get())
    Gr1.E = float(entry_E.get())
    ## G2
    if P1.TYPE!=0:
        Gs2.M = float(entry_m.get())
        Gp2.M = float(entry_m.get())
        Gr2.M = float(entry_m.get())
        Gs2.X = float(entry_Gs2X.get())
        Gs2.B = float(entry_B.get())
        Gp2.B = float(entry_B.get())
        Gr2.B = float(entry_B.get())
        Gs2.A = float(entry_A.get())
        Gp2.A = float(entry_A.get())
        Gr2.A = float(entry_A.get())
        Gs2.D = float(entry_D.get())
        Gp2.D = float(entry_D.get())
        Gr2.D = float(entry_D.get())
        Gs2.ALPHA = float(entry_alpha.get())
        Gp2.ALPHA = float(entry_alpha.get())
        Gr2.ALPHA = float(entry_alpha.get())
        Gs2.C = float(entry_C.get())
        Gp2.C = float(entry_C.get())
        Gr2.C = float(entry_C.get())
        Gs2.E = float(entry_E.get())
        Gp2.E = float(entry_E.get())
        Gr2.E = float(entry_E.get())

def finalize_parameters():
    ## M, Z
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
    ## X
    Gp1.X = -Gs1.X
    Gr1.X = Gs1.X
    if P1.TYPE!=0:
        Gp2.X = -Gs2.X
        Gr2.X = Gs2.X

def calcGPG():
    ## PGS Calc
    P1.Calc()
    P1.Output()
    P1.Checks()
    finalize_parameters()
    ## Gear Calc
    Gs1.Calc()
    Gp1.Calc()
    Gr1.Calc()
    if P1.TYPE!=0:
        Gs2.Calc()
        Gp2.Calc()
        Gr2.Calc()

def Rotate(Xin,Yin,Angle):
    Xout = np.cos(Angle)*Xin - np.sin(Angle)*Yin
    Yout = np.sin(Angle)*Xin + np.cos(Angle)*Yin
    return Xout,Yout

def PlotPGS():
    plt.figure("PGS",figsize=(6,6))
    plt.clf() # Clear figure
    if int(entry_PlotOption.get())==1 or int(entry_PlotOption.get())==3:
        # Plot Gs1
        Sun_Angle = 0.0
        if Gp1.Z%2==0:
            Sun_Angle = (2*np.pi/Gs1.Z)/2
        Gs1_X, Gs1_Y = Rotate(Gs1.X8,Gs1.Y8,Sun_Angle)
        plt.plot(Gs1_X,Gs1_Y,'dimgray')
        plt.plot(Gs1.Xp,Gs1.Yp,'r:')
        # Plot Gp1
        Gp1_Array_Angle = 2*np.pi/P1.Np
        for i in range(0,P1.Np):
            Gp1_Array_X, Gp1_Array_Y = Rotate(Gp1.X8,Gp1.Y8,Gp1_Array_Angle*i)
            Gp1_Array_Xp, Gp1_Array_Yp = Rotate(Gp1.Xp,Gp1.Yp,Gp1_Array_Angle*i)
            plt.plot(Gp1_Array_X,Gp1_Array_Y,'dimgray')
            plt.plot(Gp1_Array_Xp,Gp1_Array_Yp,'r:')
        # Plot Gr1
        plt.plot(Gr1.X8,Gr1.Y8,'dimgray')
        plt.plot(Gr1.Xp,Gr1.Yp,'r:')
    if int(entry_PlotOption.get())==2 or int(entry_PlotOption.get())==3:
        # Plot Gs2
        if P1.TYPE!=0:
            Sun_Angle = 0.0
            if Gp2.Z%2==0:
                Sun_Angle = (2*np.pi/Gs2.Z)/2
            Gs2_X, Gs2_Y = Rotate(Gs2.X8,Gs2.Y8,Sun_Angle)
            plt.plot(Gs2_X,Gs2_Y,'black')
            plt.plot(Gs2.Xp,Gs2.Yp,'r--')
        # Plot Gp2
        if P1.TYPE!=0:
            Gp2_Array_Angle = 2*np.pi/P1.Np
            for i in range(0,P1.Np):
                Gp2_Array_X, Gp2_Array_Y = Rotate(Gp2.X8,Gp2.Y8,Gp2_Array_Angle*i)
                Gp2_Array_Xp, Gp2_Array_Yp = Rotate(Gp2.Xp,Gp2.Yp,Gp2_Array_Angle*i)
                plt.plot(Gp2_Array_X,Gp2_Array_Y,'black')
                plt.plot(Gp2_Array_Xp,Gp2_Array_Yp,'r--')
        # Plot Gr2
        if P1.TYPE!=0:
            plt.plot(Gr2.X8,Gr2.Y8,'black')
            plt.plot(Gr2.Xp,Gr2.Yp,'r--')
    # Plot show
    plt.axis("equal")
    plt.grid(True)
    if int(entry_PlotOption.get())==1:
        plt.savefig('./Result/PGS1.png',dpi=100)
    elif int(entry_PlotOption.get())==2:
        plt.savefig('./Result/PGS2.png',dpi=100)
    else:
        plt.savefig('./Result/PGS.png',dpi=100)
    plt.show()

def OutputText():
    ## Head
    textbox.delete("0.0", "end")
    textbox.insert("0.0", "# PGS - Planetary Gear Sizing Program\n\n")
    textbox.insert("end", "![](./PGS.png)\n\n")
    ### Check Geometrical Conditions 
    textbox.insert("end","## Check Geometrical Conditions\n")
    textbox.insert("end","* Sequential Mesh Condition (Non-Factorizing, Not Required) 1 : "+P1.NonFactorizing1+"\n")
    if P1.TYPE!=0:
        textbox.insert("end","* Sequential Mesh Condition (Non-Factorizing, Not Required) 2 : "+P1.NonFactorizing2+"\n")
    textbox.insert("end","* Planet Numbers (Equal Distance Condition) 1 : "+P1.EqualDistance1+"\n")
    if P1.TYPE!=0:
        textbox.insert("end","* Planet Numbers (Equal Distance Condition) 2 : "+P1.EqualDistance2+"\n")
    textbox.insert("end","* Planets Interference (Non-Overlap Condition) 1 : "+P1.PlanetsInterference1+"\n")
    if P1.TYPE!=0:
        textbox.insert("end","* Planets Interference (Non-Overlap Condition) 2 : "+P1.PlanetsInterference2+"\n")
    textbox.insert("end","* Involute Interference Condition 1 : "+P1.InvoluteInterference1+"\n")
    if P1.TYPE!=0:
        textbox.insert("end","* Involute Interference Condition 2 : "+P1.InvoluteInterference2+"\n")
    textbox.insert("end","* Trimming Interference 1 : "+P1.TrimmingInterference1+"\n")
    if P1.TYPE!=0:
        textbox.insert("end","* Trimming Interference 2 : "+P1.TrimmingInterference2+"\n")
    textbox.insert("end","* Teeth Numbers which is Integer 1 : "+P1.TeethNumberInteger1+"\n")
    if P1.TYPE!=0:
        textbox.insert("end","* Teeth Numbers which is Integer 2 : "+P1.TeethNumberInteger2+"\n")
    textbox.insert("end","\n")
    ### Input Parameters
    textbox.insert("end","## Input Parameters\n")
    textbox.insert("end","* Type, TYPE = "+str(int(P1.TYPE))+"\n")
    textbox.insert("end","* Module, m = "+str(float(P1.m))+"\n")
    textbox.insert("end","* Planets Number, Np = "+str(int(P1.Np))+"\n")
    textbox.insert("end","* Zr2/Np = "+str(int(P1.Zr2_MultipleNp))+"\n")
    textbox.insert("end","* Zs1/Np = "+str(int(P1.Zs1_MultipleNp))+"\n")
    textbox.insert("end","* Shift Factor, Gs1.X = "+str(float(Gs1.X))+"\n")
    textbox.insert("end","* Shift Factor, Gs2.X = "+str(float(Gs2.X))+"\n")
    textbox.insert("end","* Backlash Factor, B = "+str(float(Gs1.B))+"\n")
    textbox.insert("end","* Addendum Factor, A = "+str(float(Gs1.A))+"\n")
    textbox.insert("end","* Dedendum Factor, D = "+str(float(Gs1.D))+"\n")
    textbox.insert("end","* Pressure Angle, alpha = "+str(float(Gs1.ALPHA))+"\n")
    textbox.insert("end","* Radius of Hib End, C = "+str(float(Gs1.C))+"\n")
    textbox.insert("end","* Radius of Tooth End, E = "+str(float(Gs1.E))+"\n\n")
    ### P1
    if P1.TYPE!=0:
        textbox.insert("end","## Wolfrom Planetary Gear Set"+"\n\n")
        textbox.insert("end","### Ratio"+"\n")
        textbox.insert("end","* Ratio (Sun-Planet1) = "+str(P1.Gp1s)+"\n")
        textbox.insert("end","* Ratio (Planet2-Ring2) = "+str(P1.Gr2p2)+"\n")
        textbox.insert("end","* Ratio Total (Ring2 Fiexed, Carrier Output) = "+str(P1.G1)+"\n")
        textbox.insert("end","* Ratio Total (Carrier Fixed, Ring2 Output) = "+str(P1.G2)+"\n")
        temp1 = int(Gr2.Z*Gp1.Z*Gs1.Z+Gr2.Z*Gp1.Z*Gr1.Z)
        temp2 = int(Gs1.Z*Gr2.Z*Gp1.Z-Gs1.Z*Gr1.Z*Gp2.Z)
        temp3 = np.gcd(temp1,temp2)
        textbox.insert("end","* Ratio Total (Type-3K : Carrier Free, Ring2 Output) = "+str(P1.G22)+" = "+str(int(temp1/temp3))+"/"+str(int(temp2/temp3))+"\n\n")
        textbox.insert("end","### Size"+"\n")
        textbox.insert("end","* Sun1 = "+str(P1.Ds1)+" [mm],  "+str(P1.Zs1)+" [ea]"+"\n")
        textbox.insert("end","* Planet1 = "+str(P1.Dp1)+" [mm],  "+str(P1.Zp1)+" [ea]"+"\n")
        textbox.insert("end","* Ring1 = "+str(P1.Dr1)+" [mm],  "+str(P1.Zr1)+" [ea]"+"\n")
        textbox.insert("end","* Sun2 = "+str(P1.Ds2)+" [mm],  "+str(P1.Zs2)+" [ea]"+"\n")
        textbox.insert("end","* Planet2 = "+str(P1.Dp2)+" [mm],  "+str(P1.Zp2)+" [ea]"+"\n")
        textbox.insert("end","* Ring2 = "+str(P1.Dr2)+" [mm],  "+str(P1.Zr2)+" [ea]"+"\n")
        textbox.insert("end","* Radius of Carrier = "+str(P1.Dc/2)+" [mm]"+"\n")
        textbox.insert("end","* Number of Planets = "+str(P1.Np)+" [ea]"+"\n\n")
    else:
        textbox.insert("end","## Simple Planetary Gear Set"+"\n\n")
        textbox.insert("end","### Ratio"+"\n")
        textbox.insert("end","* Ratio (Sun-Planet1) = "+str(P1.Gp1s)+"\n")
        textbox.insert("end","* Ratio (Total, Carrier Output) (1-stage) = "+str(P1.G3)+"\n")
        textbox.insert("end","* Ratio (Total, Carrier Output) (2-stages) = "+str(P1.G3**2)+"\n")
        textbox.insert("end","* Ratio (Total, Carrier Output) (3-stages) = "+str(P1.G3**3)+"\n")
        textbox.insert("end","* Ratio (Total, Ring1 Output) (1-stage) = "+str(P1.G4)+"\n")
        textbox.insert("end","* Ratio (Total, Ring1 Output) (2-stages) = "+str(P1.G4**2)+"\n")
        textbox.insert("end","* Ratio (Total, Ring1 Output) (3-stages) = "+str(P1.G4**3)+"\n\n")
        textbox.insert("end","### Size"+"\n")
        textbox.insert("end","* Sun1 = "+str(P1.Ds1)+" [mm],  "+str(P1.Zs1)+" [ea]"+"\n")
        textbox.insert("end","* Planet1 = "+str(P1.Dp1)+" [mm],  "+str(P1.Zp1)+" [ea]"+"\n")
        textbox.insert("end","* Ring1 = "+str(P1.Dr1)+" [mm],  "+str(P1.Zr1)+" [ea]"+"\n")
        textbox.insert("end","* Radius of Carrier = "+str(P1.Dc/2)+" [mm]"+"\n")
        textbox.insert("end","* Number of Planets = "+str(P1.Np)+" [ea]"+"\n\n")
    ### Gs1, Gp1, Gr1, Gs2, Gp2, Gr2
    temp = ['Gs1', 'Gp1', 'Gr1']
    if P1.TYPE!=0:
        temp = ['Gs1', 'Gp1', 'Gr1', 'Gs2', 'Gp2', 'Gr2']
    for i in temp:
        textbox.insert("end","### "+str(i)+"\n")
        textbox.insert("end","* Module = "+str(eval(i).M)+" [mm]"+"\n")
        textbox.insert("end","* Pressure Angle = "+str(eval(i).ALPHA)+" [deg]"+"\n")
        if str(i)=='Gr1' or str(i)=='Gr2':
            textbox.insert("end","* Teeth Number = -"+str(eval(i).Z)+" [ea]"+"\n")
        else:
            textbox.insert("end","* Teeth Number = "+str(eval(i).Z)+" [ea]"+"\n")
        textbox.insert("end","* Offset Factor = "+str(eval(i).X)+""+"\n")
        textbox.insert("end","* Offset = "+str(eval(i).X*eval(i).M)+" [mm]"+"\n")
        textbox.insert("end","* Backlash Factor = "+str(eval(i).B)+""+"\n")
        textbox.insert("end","* Backlash = "+str(eval(i).B*eval(i).M)+" [mm]"+"\n")
        textbox.insert("end","* Addendum Factor = "+str(eval(i).A)+""+"\n")
        textbox.insert("end","* Addendum = "+str(eval(i).A*eval(i).M)+" [mm]"+"\n")
        textbox.insert("end","* Dedendum Factor = "+str(eval(i).D)+""+"\n")
        textbox.insert("end","* Dedendum = "+str(eval(i).D*eval(i).M)+" [mm]"+"\n")
        textbox.insert("end","* Total Tooth Height = "+str((eval(i).A+eval(i).D)*eval(i).M)+" [mm]"+"\n")
        textbox.insert("end","* Base Circle Dia = "+str(eval(i).M*eval(i).Z*np.cos(np.deg2rad(eval(i).ALPHA)))+" [mm]"+"\n")
        textbox.insert("end","* Pitch Circle Dia = "+str(eval(i).M*eval(i).Z)+" [mm]"+"\n")
        textbox.insert("end","* Offset Circle Dia = "+str(2*eval(i).M*(eval(i).Z/2+eval(i).X))+" [mm]"+"\n")
        textbox.insert("end","* Root Circle Dia = "+str(2*eval(i).M*(eval(i).Z/2+eval(i).X-eval(i).D))+" [mm]"+"\n")
        textbox.insert("end","* Outer Circle Dia = "+str(2*eval(i).M*(eval(i).Z/2+eval(i).X+eval(i).A))+" [mm]"+"\n\n")

def save_parameters():
    WorkingDirectory = "./Result"
    temp = ['Gs1', 'Gp1', 'Gr1']
    if P1.TYPE!=0:
        temp = ['Gs1', 'Gp1', 'Gr1', 'Gs2', 'Gp2', 'Gr2']
    os.makedirs(WorkingDirectory, exist_ok=True)
    f1=open(WorkingDirectory+'/PGS.md','w')
    f1.write(textbox.get('0.0','end'))
    f1.close()
    for i in temp:
        temp2 = WorkingDirectory+"/"+i
        os.makedirs(temp2, exist_ok=True)
        f2=open(temp2+'/Inputs.csv','w')
        f2.write('parameter,value'+'\n')
        f2.write('m,'+str(eval(i).M)+'\n')
        f2.write('z,'+str(eval(i).Z)+'\n')
        f2.write('alpha,'+str(eval(i).ALPHA)+'\n')
        f2.write('x,'+str(eval(i).X)+'\n')
        f2.write('b,'+str(eval(i).B)+'\n')
        f2.write('a,'+str(eval(i).A)+'\n')
        f2.write('d,'+str(eval(i).D)+'\n')
        f2.write('c,'+str(eval(i).C)+'\n')
        f2.write('e,'+str(eval(i).E)+'\n')
        f2.write('x_0,'+str(eval(i).X_0)+'\n')
        f2.write('y_0,'+str(eval(i).Y_0)+'\n')
        f2.write('seg_circle,'+str(eval(i).SEG_CIRCLE)+'\n')
        f2.write('seg_involute,'+str(eval(i).SEG_INVOLUTE)+'\n')
        f2.write('seg_edge_r,'+str(eval(i).SEG_EDGE_R)+'\n')
        f2.write('seg_root_r,'+str(eval(i).SEG_ROOT_R)+'\n')
        f2.write('seg_outer,'+str(eval(i).SEG_OUTER)+'\n')
        f2.write('seg_root,'+str(eval(i).SEG_ROOT)+'\n')
        f2.write('scale,'+'0.7'+'\n')
        f2.close()

################
# Callback
def button_run_callback():
    read_parameters()
    calcGPG()
    OutputText()
    save_parameters()
    PlotPGS()

def button_exit_callback():
    print("button_exit pressed")
    exit()

################
# GUI Setting
customtkinter.set_default_color_theme("green")
app = customtkinter.CTk()
app.title("PGS with customtkinter")
app.geometry("950x600")
app.resizable(width=False, height=False)
font16 = customtkinter.CTkFont(size=16)
if ( sys.platform.startswith('win')): app.iconbitmap('PGS.ico')
## Gap between pads in customtkinter
PADX = 1
PADY = 1

## Subject
label_P1 = customtkinter.CTkLabel(app, text="# Planetary System", fg_color="transparent", compound="right", font=font16)
label_P1.grid(row=0, column=0, padx=PADX, pady=PADY, sticky="w")

## Type, TYPE
label1_TYPE = customtkinter.CTkLabel(app, text="Type, TYPE = ", fg_color="transparent", compound="right")
label1_TYPE.grid(row=1, column=0, padx=PADX, pady=PADY, sticky="e")
entry_TYPE = customtkinter.CTkEntry(app, placeholder_text="1")
entry_TYPE.grid(row=1, column=1, padx=PADX, pady=PADY)
label2_TYPE = customtkinter.CTkLabel(app, text="0=Simple, 1=Wolfrom(diff=1), 2=Wolfrom(diff=0.5), 3=Wolfrom(diff=2)", fg_color="transparent", compound="left")
label2_TYPE.grid(row=2, column=1, padx=PADX, pady=PADY, sticky="w", columnspan=3)

## Module, m
label1_m = customtkinter.CTkLabel(app, text="Module, m = ", fg_color="transparent", compound="right")
label1_m.grid(row=3, column=0, padx=PADX, pady=PADY, sticky="e")
entry_m = customtkinter.CTkEntry(app, placeholder_text="1.0")
entry_m.grid(row=3, column=1, padx=PADX, pady=PADY)
label2_m = customtkinter.CTkLabel(app, text="[mm] > 0", fg_color="transparent", compound="left")
label2_m.grid(row=3, column=2, padx=PADX, pady=PADY, sticky="w")

## Planets Number, Np
label1_Np = customtkinter.CTkLabel(app, text="Planets Number, Np = ", fg_color="transparent", compound="right")
label1_Np.grid(row=4, column=0, padx=PADX, pady=PADY, sticky="e")
entry_Np = customtkinter.CTkEntry(app, placeholder_text="4")
entry_Np.grid(row=4, column=1, padx=PADX, pady=PADY)
label2_Np = customtkinter.CTkLabel(app, text="[ea] > 2", fg_color="transparent", compound="left")
label2_Np.grid(row=4, column=2, padx=PADX, pady=PADY, sticky="w")

## Zr2/Np
label1_Zr2overNp = customtkinter.CTkLabel(app, text="Zr2/Np = ", fg_color="transparent", compound="right")
label1_Zr2overNp.grid(row=5, column=0, padx=PADX, pady=PADY, sticky="e")
entry_Zr2overNp = customtkinter.CTkEntry(app, placeholder_text="15")
entry_Zr2overNp.grid(row=5, column=1, padx=PADX, pady=PADY)
label2_Zr2overNp = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_Zr2overNp.grid(row=5, column=2, padx=PADX, pady=PADY, sticky="w")

## Zs1/Np
label1_Zs1overNp = customtkinter.CTkLabel(app, text="Zs1/Np = ", fg_color="transparent", compound="right")
label1_Zs1overNp.grid(row=6, column=0, padx=PADX, pady=PADY, sticky="e")
entry_Zs1overNp = customtkinter.CTkEntry(app, placeholder_text="8")
entry_Zs1overNp.grid(row=6, column=1, padx=PADX, pady=PADY)
label2_Zs1overNp = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_Zs1overNp.grid(row=6, column=2, padx=PADX, pady=PADY, sticky="w")

## Subject
label_G = customtkinter.CTkLabel(app, text="# Involute Gear Spec", fg_color="transparent", compound="right", font=font16)
label_G.grid(row=7, column=0, padx=PADX, pady=PADY, sticky="w")

## Shift Factor, Gs1.X
label1_Gs1X = customtkinter.CTkLabel(app, text="Shift Factor, Gs1.X = ", fg_color="transparent", compound="right")
label1_Gs1X.grid(row=8, column=0, padx=PADX, pady=PADY, sticky="e")
entry_Gs1X = customtkinter.CTkEntry(app, placeholder_text="0.0")
entry_Gs1X.grid(row=8, column=1, padx=PADX, pady=PADY)
label2_Gs1X = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_Gs1X.grid(row=8, column=2, padx=PADX, pady=PADY, sticky="w")

## Shift Factor, Gs2.X
label1_Gs2X = customtkinter.CTkLabel(app, text="Shift Factor, Gs2.X = ", fg_color="transparent", compound="right")
label1_Gs2X.grid(row=9, column=0, padx=PADX, pady=PADY, sticky="e")
entry_Gs2X = customtkinter.CTkEntry(app, placeholder_text="0.0")
entry_Gs2X.grid(row=9, column=1, padx=PADX, pady=PADY)
label2_Gs2X = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_Gs2X.grid(row=9, column=2, padx=PADX, pady=PADY, sticky="w")

## Backlash Factor, B
label1_B = customtkinter.CTkLabel(app, text="Backlash Factor, B = ", fg_color="transparent", compound="right")
label1_B.grid(row=10, column=0, padx=PADX, pady=PADY, sticky="e")
entry_B = customtkinter.CTkEntry(app, placeholder_text="0.0")
entry_B.grid(row=10, column=1, padx=PADX, pady=PADY)
label2_B = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_B.grid(row=10, column=2, padx=PADX, pady=PADY, sticky="w")

## Addendum Factor, A
label1_A = customtkinter.CTkLabel(app, text="Addendum Factor, A = ", fg_color="transparent", compound="right")
label1_A.grid(row=11, column=0, padx=PADX, pady=PADY, sticky="e")
entry_A = customtkinter.CTkEntry(app, placeholder_text="1.0")
entry_A.grid(row=11, column=1, padx=PADX, pady=PADY)
label2_A = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_A.grid(row=11, column=2, padx=PADX, pady=PADY, sticky="w")

## Dedendum Factor, D
label1_D = customtkinter.CTkLabel(app, text="Dedendum Factor, D = ", fg_color="transparent", compound="right")
label1_D.grid(row=12, column=0, padx=PADX, pady=PADY, sticky="e")
entry_D = customtkinter.CTkEntry(app, placeholder_text="1.25")
entry_D.grid(row=12, column=1, padx=PADX, pady=PADY)
label2_D = customtkinter.CTkLabel(app, text="...", fg_color="transparent", compound="left")
label2_D.grid(row=12, column=2, padx=PADX, pady=PADY, sticky="w")

## Pressure Angle, alpha
label1_alpha = customtkinter.CTkLabel(app, text="Pressure Angle, alpha = ", fg_color="transparent", compound="right")
label1_alpha.grid(row=13, column=0, padx=PADX, pady=PADY, sticky="e")
entry_alpha = customtkinter.CTkEntry(app, placeholder_text="20.0")
entry_alpha.grid(row=13, column=1, padx=PADX, pady=PADY)
label2_alpha = customtkinter.CTkLabel(app, text="[deg]", fg_color="transparent", compound="left")
label2_alpha.grid(row=13, column=2, padx=PADX, pady=PADY, sticky="w")

## Radius of Hob End, C
label1_C = customtkinter.CTkLabel(app, text="Radius of Hob End, C = ", fg_color="transparent", compound="right")
label1_C.grid(row=14, column=0, padx=PADX, pady=PADY, sticky="e")
entry_C = customtkinter.CTkEntry(app, placeholder_text="0.2")
entry_C.grid(row=14, column=1, padx=PADX, pady=PADY)
label2_C = customtkinter.CTkLabel(app, text="[mm]", fg_color="transparent", compound="left")
label2_C.grid(row=14, column=2, padx=PADX, pady=PADY, sticky="w")

## Radius of Tooth End, E
label1_E = customtkinter.CTkLabel(app, text="Radius of Tooth End, E = ", fg_color="transparent", compound="right")
label1_E.grid(row=15, column=0, padx=PADX, pady=PADY, sticky="e")
entry_E = customtkinter.CTkEntry(app, placeholder_text="0.1")
entry_E.grid(row=15, column=1, padx=PADX, pady=PADY)
label2_E = customtkinter.CTkLabel(app, text="[mm]", fg_color="transparent", compound="left")
label2_E.grid(row=15, column=2, padx=PADX, pady=PADY, sticky="w")

## Plot Options
label1_PlotOption = customtkinter.CTkLabel(app, text="Plot Options = ", fg_color="transparent", compound="right", font=font16)
label1_PlotOption.grid(row=16, column=0, padx=PADX, pady=PADY, sticky="e")
entry_PlotOption = customtkinter.CTkEntry(app, placeholder_text="1")
entry_PlotOption.grid(row=16, column=1, padx=PADX, pady=PADY)
label2_PlotOption = customtkinter.CTkLabel(app, text="1=Stage1, 2=Stage2, 3=Total", fg_color="transparent", compound="left")
label2_PlotOption.grid(row=17, column=1, padx=PADX, pady=PADY, sticky="w")

## Button Run
button_run = customtkinter.CTkButton(app, text="Run", command=button_run_callback, width=100)
button_run.grid(row=20, column=0, padx=PADX, pady=PADY, sticky="e")

## Button exit
button_exit = customtkinter.CTkButton(app, text="Exit", command=button_exit_callback, width=100)
button_exit.grid(row=20, column=5, padx=PADX, pady=PADY, sticky="e")

## Textbox
textbox = customtkinter.CTkTextbox(master=app, width=550, corner_radius=0)
textbox.grid(row=3, column=3, sticky="nsew", rowspan=15, columnspan=3)
textbox.delete("0.0", "end")
textbox.insert("end", "\n########################################")
textbox.insert("end", "\n#")
textbox.insert("end", "\n# PGS - Planetary Gear Sizing Program")
textbox.insert("end", "\n# https://github.com/dymaxionkim/PGS")
textbox.insert("end", "\n#")
textbox.insert("end", "\n########################################")
textbox.insert("end", "\n\n1. Input Parameters.")
textbox.insert("end", "\n2. Press Run.")

################
# App Start
## Planetary Gear Sizing Class
P1 = PGS()
## Gear Class
Gs1 = GPG()
Gp1 = GPG()
Gr1 = GPG()
Gs2 = GPG()
Gp2 = GPG()
Gr2 = GPG()
# Init
init_parameters()
read_parameters()
calcGPG()
# GUI Loop
app.mainloop()
