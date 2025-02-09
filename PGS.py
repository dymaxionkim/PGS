import numpy as np

class PGS:
    def __init__(self):
        self.TYPE = 0 # 0=Simple, 1=Wolfrom(diff=1), 2=Wolfrom(diff=0.5), 3=Wolfrom(diff=2)
        self.alpha = 20.0 # Pressure Angle [deg]
        self.m = 0.5 # Common Module
        self.Np = 4  # Planets Number (it must be even number)
        self.Zr2_MultipleNp = 15
        self.Zs1_MultipleNp = 4

    def Calc(self):
        # Calc
        self.m1 = self.m # Module1
        self.m2 = self.m # Module2 (No need for Simple Type)
        if self.TYPE==2:
            self.TYPE_DIFF=0.5
        elif self.TYPE==3:
            self.TYPE_DIFF=2.0
        else:
            self.TYPE_DIFF=1.0
        self.Zr1_MultipleNp = self.Zr2_MultipleNp+self.TYPE_DIFF
        self.Zs1 = self.Zs1_MultipleNp*self.Np # Teeth Number of Sun
        self.Zr1 = -self.Zr1_MultipleNp*self.Np # Teeth Number of Ring1
        self.Zp1 = (-self.Zr1-self.Zs1)/2 # Teeth Number of Planet1
        self.Ds1 = self.Zs1*self.m1 # Dia of Sun1
        self.Dp1 = self.Zp1*self.m1 # Dia of Planet1
        self.Dr1 = -self.Zr1*self.m1 # Dia of Ring1
        self.Dc = self.Ds1+self.Dp1 # Dia of Carrier
        self.Gp1s = self.Dp1/self.Ds1 # Ratio of Planet1-Sun
        if self.TYPE!=0:
            self.Zr2 = -self.Zr2_MultipleNp*self.Np # Teeth Number of Ring2
            self.Zp2 = ((-self.Zr2*self.m2)-self.Dc)/(self.m2) # Teeth Number of Planet2 (No need for Simple Type)
            self.Dp2 = self.Zp2*self.m2 # Dia of Planet2
            self.Ds2 = self.Dc-self.Dp2 # Dia of Sun2
            self.Zs2 = self.Ds2/self.m2 # Teeth Number of Sun2
            self.Dr2 = -self.Zr2*self.m2 # Dia of Ring2
            self.Gr2p2 = self.Dr2/self.Dp2 # Ratio of Ring-Planet2    
            self.G1 = round(1+self.Gr2p2*self.Gp1s,6) # Ratio Total (Ring2 Fiexed, Carrier Output)
            self.G2 = -round(self.Gr2p2*self.Gp1s,6) # Ratio Total (Carrier Fixed, Ring2 Output)
            self.L1 = self.Dr1/self.Ds1
            self.L2 = (self.Dr1*self.Dp2)/(self.Dr2*self.Dp1)
            self.G22 = round((1+self.L1)/(1-self.L2),6) # Ratio Total (Type-3K : Carrier Free, Ring Output)
            if self.L2>1:
                self.G22 = -self.G22
        else:
            self.G3 = round(1-self.Zr1/self.Zs1,6) # Ratio Total (Carrier Output)
            self.G4 = -round(-self.Zr1/self.Zs1,6) # Ratio Total (Ring1 Output)

    def Output(self):
        # Output
        if self.TYPE!=0:
            print("\n##### Wolfrom Planetary Gear Set")
            print("### Ratio")
            print("Ratio (Sun-Planet1) = ",self.Gp1s,"")
            print("Ratio (Planet2-Ring2) = ",self.Gr2p2,"")
            print("Ratio Total (Ring2 Fiexed, Carrier Output) = ",self.G1,"")
            print("Ratio Total (Carrier Fixed, Ring2 Output) = ",self.G2,"")
            print("Ratio Total (Type-3K : Carrier Free, Ring2 Output) = ",self.G22,"")
            print("### Size")
            print("Sun = ",self.Ds1," [mm],  ",self.Zs1," [ea]")
            print("Planet1 = ",self.Dp1," [mm],  ",self.Zp1," [ea]")
            print("Ring1 = ",self.Dr1," [mm],  ",self.Zr1," [ea]")
            print("Planet2 = ",self.Dp2," [mm],  ",self.Zp2," [ea]")
            print("Ring2 = ",self.Dr2," [mm],  ",self.Zr2," [ea]")
        else:
            print("\n##### Simple Planetary Gear Set")
            print("### Ratio")
            print("Ratio (Sun-Planet1) = ",self.Gp1s,"")
            print("Ratio (Total, Carrier Output) = ",self.G3," (1-stage),  ",self.G3**2," (2-stages),  ",self.G3**3," (3-stages)")
            print("Ratio (Total, Ring1 Output) = ",self.G4," (1-stage),  ",self.G4**2," (2-stages),  ",self.G4**3," (3-stages)")
            print("### Size")
            print("Sun = ",self.Ds1," [mm],  ",self.Zs1," [ea]")
            print("Planet1 = ",self.Dp1," [mm],  ",self.Zp1," [ea]")
            print("Ring1 = ",self.Dr1," [mm],  ",self.Zr1," [ea]")

    def Checks(self):
        # Checks
        print("\n\n### Checks")
        ### ������ �������� ������ �¹��� ������ ġ���� ���°� ���� �ٸ��� Ȯ��
        ### ������ �� ���� �߻��ϵ��� �ϴ� ���� (���û���)
        ## Sequential Mesh Condition (Non-Factorizing) 1
        print("# Sequential Mesh Condition (Non-Factorizing, Not Required) 1 : ")
        if (self.Zs1%self.Np)!=0 and (-self.Zr1%self.Np)!=0:
            print("Good for noise")
            self.NonFactorizing1 = "Good for noise"
        else:
            print("No good for noise")
            self.NonFactorizing1 = "No good for noise"
        ## Sequential Mesh Condition (Non-Factorizing) 2
        if self.TYPE!=0:
            print("# Sequential Mesh Condition (Non-Factorizing, Not Required) 2 : ")
            if (self.Zs2%self.Np)!=0 and (-self.Zr2%self.Np)!=0:
                print("Good for noise")
                self.NonFactorizing2 = "Good for noise"
            else:
                print("No good for noise")
                self.NonFactorizing2 = "No good for noise"
        ### ��� ��ġ����
        ### ������ ������ ������ �ΰ� ��ġ�Ǿ�� ��
        ## Check Planets Numbers (Equal Distance Condition) 1
        print("# Planet Numbers (Equal Distance Condition) 1 : ")
        if self.TYPE==2:
            if (self.Zs1-self.Zr1)%(self.Np*self.TYPE_DIFF)==0:
                print("OK")
                self.EqualDistance1 = "OK"
            else:
                print("Fail")
                self.EqualDistance1 = "Fail"
        else:
            if (self.Zs1-self.Zr1)%self.Np==0:
                print("OK")
                self.EqualDistance1 = "OK"
            else:
                print("Fail")
                self.EqualDistance1 = "Fail"
        ## Check Planets Numbers (Equal Distance Condition) 2
        print("# Planet Numbers (Equal Distance Condition) 2 : ")
        if self.TYPE!=0:
            if -self.Zr2%self.Np==0:
                print("OK")
                self.EqualDistance2 = "OK"
            else:
                print("Fail")
                self.EqualDistance2 = "Fail"
        ### ��ø ���� ����
        ### ������� ���̿� ��ø�� ����� ��
        ## Check Planets Interference (Non-Overlap Condition) 1
        print("# Planets Interference (Non-Overlap Condition) 1 : ")
        if self.alpha==20 and self.Np<(np.pi/np.arcsin((self.Zp1+2)/(self.Zp1+self.Zs1))):
            print("OK")
            self.PlanetsInterference1 = "OK"
        else:
            print("Fail")
            self.PlanetsInterference1 = "Fail"
        ## Check Planets Interference (Non-Overlap Condition) 2
        if self.TYPE!=0:
            print("# Planets Interference (Non-Overlap Condition) 2 : ")
            if self.alpha==20 and self.Np<(np.pi/np.arcsin((self.Zp2+2)/(self.Zp2+self.Zs2))):
                print("OK")
                self.PlanetsInterference2 = "OK"
            else:
                print("Fail")
                self.PlanetsInterference2 = "Fail"
        if self.alpha!=20:
            print("No Check (Non-Standard) ")
        ### �κ���Ʈ ��������
        ### ��������� �ռ��� ���� ��, ��������� �̻Ѹ��� ������� �̳��� ������ ����ų �� ����
        ## Check Involute Interference Condition 1
        print("# Involute Interference Condition 1 : ")
        temp=(self.Zp1*np.sin(np.deg2rad(self.alpha)))**2
        temp2 = (temp-4)/(2*temp-4)
        if self.alpha==20 and -self.Zr1>=temp2:
            print("OK")
            self.InvoluteInterference1 = "OK"
        else:
            print("Fail")
            self.InvoluteInterference1 = "Fail"
        ## Check Involute Interference Condition 2
        if self.TYPE!=0:
            print("# Involute Interference Condition 2 : ")
            temp=(self.Zp2*np.sin(np.deg2rad(self.alpha)))**2
            temp2 = (temp-4)/(2*temp-4)
            if self.alpha==20 and -self.Zr2>=temp2:
                print("OK")
                self.InvoluteInterference2 = "OK"
            else:
                print("Fail")
                self.InvoluteInterference2 = "Fail"
        if self.alpha!=20:
            print("No Check (Non-Standard) ")
        ### Ʈ���� ��������
        ### ���� ������ ������ ��, �߽ɿ��� �ܰ����� �����ִ� ��� ���� �߻� ����
        ### Ʈ���� ������ ���ϱ� ���ؼ��� +���� ������ �ָ� ������
        ## Check Trimming Interference 1
        print("# Trimming Interference 1 : ")
        if self.alpha==20 and (-self.Zr1-self.Zp1)>=16:
            print("OK")
            self.TrimmingInterference1 = "OK"
        else:
            print("Fail")
            self.TrimmingInterference1 = "Fail"
        ## Check Trimming Interference 2
        if self.TYPE!=0:
            print("# Trimming Interference 2 : ")
            if self.alpha==20 and (-self.Zr2-self.Zp2)>=16:
                print("OK")
                self.TrimmingInterference2 = "OK"
            else:
                print("Fail")
                self.TrimmingInterference2 = "Fail"
        if self.alpha!=20:
            print("No Check (Non-Standard) ")
            self.TrimmingInterference1 = "No Check (Non-Standard)"
        ### �� ����� �ռ��� �������� ���� �Ǻ�
        ## Check Teeth Numbers which is Integer
        print("# Teeth Numbers which is Integer 1 : ")
        if round(float(self.Zs1),6).is_integer() and round(float(self.Zp1),6).is_integer() and round(float(self.Zr1),6).is_integer():
            print("OK")
            self.TeethNumberInteger1 = "OK"
        else:
            print("Fail")
            self.TeethNumberInteger1 = "Fail"
        if self.TYPE!=0:
            print("# Teeth Numbers which is Integer 2 : ")
            if round(float(self.Zs2),6).is_integer() and round(float(self.Zp2),6).is_integer() and round(float(self.Zr2),6).is_integer():
                print("OK")
                self.TeethNumberInteger2 = "OK"
            else:
                print("Fail")
                self.TeethNumberInteger2 = "Fail"

"""
P1 = PGS()
P1.Calc()
P1.Output()
P1.Checks()
"""