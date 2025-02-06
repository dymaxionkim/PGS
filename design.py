import numpy as np
import matplotlib.pyplot as plt
from GPG import GPG
from PGS import PGS

# Planetary Gear Sizing Class
P1 = PGS()

# PGS Spec
P1.TYPE = 1 # 0=Simple, 1=Wolfrom(diff=1), 2=Wolfrom(diff=0.5), 3=Wolfrom(diff=2)
P1.m = 0.5 # Common Module
P1.Np = 8  # Planets Number (it must be even number)
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

# Plot show
plt.axis("equal")
plt.grid("on")
plt.show()

