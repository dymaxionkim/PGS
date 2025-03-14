import numpy as np

class GPG:
    def __init__(self):
        # Gear Spec
        self.M = 1.0
        self.Z = -18
        self.ALPHA = 20
        self.X = 0.0
        self.B = 0.05
        self.A = 1.0
        self.D = 1.25
        self.C = 0.2
        self.E = 0.1
        self.X_0 = 0.0
        self.Y_0 = 0.0
        # Segments
        self.SEG_CIRCLE = 360
        self.SEG_INVOLUTE = 15
        self.SEG_EDGE_R = 5
        self.SEG_ROOT_R = 5
        self.SEG_OUTER = 5
        self.SEG_ROOT = 5
        # Caculated Parameters
        self.ALPHA_0 = 0.0 # ALPHA [rad]
        self.ALPHA_M = 0.0 # Center Line's Slope [Rad]
        self.ALPHA_IS = 0.0 # Start Angle for Involute Curve
        self.THETA_IS = 0.0 # Minimum Range of Parameter to Draw Involute Curve
        self.THETA_IE = 0.0 # Maximum Range of Parameter to Draw Involute Curve
        self.ALPHA_E = 0.0 # Angle between Tooth's Center & End Point of Tooth
        self.X_E = 0.0 # Location of Tooth's End Point
        self.Y_E = 0.0 # Location of Tooth's End Point
        self.X_E0 = 0.0 # Location of Edge Round Center
        self.Y_E0 = 0.0 # Location of Edge Round Center
        self.THETA3_MIN = 0.0 # Start Angle of Edge Round Curve
        self.THETA3_MAX = 0.0 # End Angle of Edge Round Curve
        self.ALPHA_TS = 0.0 # Start Angle of Root Round Curve
        self.THETA_TE = 0.0 # End Angle of Root Round Curve
        self.P_ANGLE = 0.0 # Gear Pitch Angle
        self.ALIGN_ANGLE = 0.0 # Gear Align Angle
        self.ROTATE_ANGLE = 0.0 # Rotate Angle
        # Linspaces
        self.THETA1 = [] # Linspace for Involute curve
        self.THETA3 = [] # Linspace for Edge Round curve
        self.THETA_T = [] # Linspace for Root Round Curve
        self.THETA_S = [] # Substitution Variable to plot Root Round Curve
        self.THETA6 = [] # Linspace for outer Arc
        self.THETA7 = [] # Linspace for root Arc
        self.X11 = [] # Involute Curve
        self.Y11 = []
        self.X21 = [] # EdgeRoundCurve
        self.Y21 = []
        self.X31 = [] # RootRoundCurve
        self.Y31 = []
        self.X41 = [] # OuterArc
        self.Y41 = []
        self.X51 = [] # RootArc
        self.Y51 = []
        self.X1 = [] # Combine1
        self.Y1 = []
        self.X2 = [] # MirrorYTooth
        self.Y2 = []
        self.X3 = [] # Combine3
        self.Y3 = []
        self.X4 = [] # ZeroAngle4
        self.Y4 = []
        self.X5 = [] # Total
        self.Y5 = []
        self.X6 = [] # MovePositionOneTooth
        self.Y6 = []
        self.X7 = [] # RotateTotalTeeth
        self.Y7 = []
        self.X8 = [] # MovePositionTotalTeeth
        self.Y8 = []
        self.Xp = [] # PitchCircle
        self.Yp = []
        self.Xo = [] # OuterCircle
        self.Yo = []
        self.Xr = [] # RootCircle
        self.Yr = []

    def Internal(self):
        if self.Z<0 :
            self.Z = -self.Z
            self.X = -self.X
            self.B = -self.B
            A_temp = self.A
            D_temp = self.D
            self.A = D_temp
            self.D = A_temp
            C_temp = self.C
            E_temp = self.E
            self.C = E_temp
            self.E = C_temp

    def Parameters(self):
        self.ALPHA_0 = self.ALPHA*(2*np.pi/360)
        self.ALPHA_M = np.pi/self.Z
        self.ALPHA_IS = self.ALPHA_0+np.pi/(2*self.Z)+self.B/(self.Z*np.cos(self.ALPHA_0))-(1+2*self.X/self.Z)*np.sin(self.ALPHA_0)/np.cos(self.ALPHA_0)
        self.THETA_IS = np.sin(self.ALPHA_0)/np.cos(self.ALPHA_0) + 2*(self.C*(1-np.sin(self.ALPHA_0))+self.X-self.D)/(self.Z*np.cos(self.ALPHA_0)*np.sin(self.ALPHA_0))
        self.THETA_IE = 2*self.E/(self.Z*np.cos(self.ALPHA_0))+np.sqrt(((self.Z+2*(self.X+self.A-self.E))/(self.Z*np.cos(self.ALPHA_0)))**2-1)
        self.ALPHA_E = self.ALPHA_IS + self.THETA_IE - np.arctan(np.sqrt(((self.Z+2*(self.X+self.A-self.E))/(self.Z*np.cos(self.ALPHA_0)))**2-1))
        self.X_E = self.M*((self.Z/2)+self.X+self.A)*np.cos(self.ALPHA_E)
        self.Y_E = self.M*((self.Z/2)+self.X+self.A)*np.sin(self.ALPHA_E)
        self.X_E0 = self.M*(self.Z/2+self.X+self.A-self.E)*np.cos(self.ALPHA_E)
        self.Y_E0 = self.M*(self.Z/2+self.X+self.A-self.E)*np.sin(self.ALPHA_E)
        self.ALPHA_TS = (2*(self.C*(1-np.sin(self.ALPHA_0))-self.D)*np.sin(self.ALPHA_0)+self.B)/(self.Z*np.cos(self.ALPHA_0))-2*self.C*np.cos(self.ALPHA_0)/self.Z+np.pi/(2*self.Z)
        self.THETA_TE = 2*self.C*np.cos(self.ALPHA_0)/self.Z - 2*(self.D-self.X-self.C*(1-np.sin(self.ALPHA_0)))*np.cos(self.ALPHA_0)/(self.Z*np.sin(self.ALPHA_0))
        # modify "E"
        if (self.ALPHA_E>self.ALPHA_M) and (self.ALPHA_M>self.ALPHA_IS+self.THETA_IE-np.arctan(self.THETA_IE)) :
            self.E = (self.E/2)*np.cos(self.ALPHA_0)*(self.THETA_IE-np.sqrt((1/np.cos(self.ALPHA_IS+self.THETA_IE-self.ALPHA_M))**2-1))
        self.P_ANGLE = 2*np.pi/self.Z
        self.ALIGN_ANGLE = np.pi/2-np.pi/self.Z

    def InvoluteCurve(self):
        self.THETA1 = np.linspace(self.THETA_IS,self.THETA_IE,self.SEG_INVOLUTE)
        self.X11 = np.ones(len(self.THETA1))
        self.X11 = (1/2)*self.M*self.Z*np.cos(self.ALPHA_0)*np.sqrt(1+self.THETA1**2)*np.cos(self.ALPHA_IS+self.THETA1-np.arctan(self.THETA1))
        self.Y11 = (1/2)*self.M*self.Z*np.cos(self.ALPHA_0)*np.sqrt(1+self.THETA1**2)*np.sin(self.ALPHA_IS+self.THETA1-np.arctan(self.THETA1))

    def EdgeRoundCurve(self):
        self.THETA3_MIN = np.arctan((self.Y11[len(self.Y11)-1]-self.Y_E0)/(self.X11[len(self.X11)-1]-self.X_E0))
        self.THETA3_MAX = np.arctan((self.Y_E-self.Y_E0)/(self.X_E-self.X_E0))
        self.THETA3 = np.linspace(self.THETA3_MIN,self.THETA3_MAX,self.SEG_EDGE_R)
        self.X21 = self.M*self.E*np.cos(self.THETA3) + self.X_E0
        self.Y21 = self.M*self.E*np.sin(self.THETA3) + self.Y_E0

    def RootRoundCurve(self):
        self.THETA_T = np.linspace(0,self.THETA_TE,self.SEG_ROOT_R)
        if (self.C!=0) and ((self.D-self.X-self.C)==0) :
            # mcÎ•? Î∞òÏ??Î¶ÑÏúºÎ°? ?ïò?äî ?õê?ò∏Î•? Í∑∏Î†§?Ñú ???Ï≤¥ÌïòÍ≤? ?ê®
            self.THETA_S = (np.pi/2)*np.ones(len(self.THETA_T))
        elif (self.D-self.X-self.C)!=0 :
            self.THETA_S = np.arctan((self.M*self.Z*self.THETA_T/2)/(self.M*self.D-self.M*self.X-self.M*self.C))
        self.X31 = self.M*((self.Z/2+self.X-self.D+self.C)*np.cos(self.THETA_T+self.ALPHA_TS)+(self.Z/2)*self.THETA_T*np.sin(self.THETA_T+self.ALPHA_TS)-self.C*np.cos(self.THETA_S+self.THETA_T+self.ALPHA_TS))
        self.Y31 = self.M*((self.Z/2+self.X-self.D+self.C)*np.sin(self.THETA_T+self.ALPHA_TS)-(self.Z/2)*self.THETA_T*np.cos(self.THETA_T+self.ALPHA_TS)-self.C*np.sin(self.THETA_S+self.THETA_T+self.ALPHA_TS))

    def OuterArc(self):
        self.THETA6 = np.linspace(self.ALPHA_E,self.ALPHA_M,self.SEG_OUTER) 
        self.X41 = self.M*(self.Z/2+self.A+self.X)*np.cos(self.THETA6)
        self.Y41 = self.M*(self.Z/2+self.A+self.X)*np.sin(self.THETA6)

    def RootArc(self):
        self.THETA7 = np.linspace(0,self.ALPHA_TS,self.SEG_ROOT) 
        self.X51 = self.M*(self.Z/2-self.D+self.X)*np.cos(self.THETA7)
        self.Y51 = self.M*(self.Z/2-self.D+self.X)*np.sin(self.THETA7)

    def Reverse(self):
        # Reverse Involute Curve
        Xtemp = np.flip(self.X11)
        Ytemp = np.flip(self.Y11)
        self.X11 = Xtemp
        self.Y11 = Ytemp
        # Reverse EdgeRoundCurve
        Xtemp = np.flip(self.X21)
        Ytemp = np.flip(self.Y21)
        self.X21 = Xtemp
        self.Y21 = Ytemp
        # Reverse RootRoundCurve
        Xtemp = np.flip(self.X31)
        Ytemp = np.flip(self.Y31)
        self.X31 = Xtemp
        self.Y31 = Ytemp
        # Reverse OuterArc
        Xtemp = np.flip(self.X41)
        Ytemp = np.flip(self.Y41)
        self.X41 = Xtemp
        self.Y41 = Ytemp
        # Reverse RootArc
        Xtemp = np.flip(self.X51)
        Ytemp = np.flip(self.Y51)
        self.X51 = Xtemp
        self.Y51 = Ytemp

    def Combine1(self):
        self.X1 = np.concatenate((self.X41,self.X21,self.X11,self.X31,self.X51))
        self.Y1 = np.concatenate((self.Y41,self.Y21,self.Y11,self.Y31,self.Y51))

    def MirrorY(self):
        self.X2 =  np.flip(self.X1)
        self.Y2 = -np.flip(self.Y1)

    def Combine3(self):
        self.X3 = np.concatenate((self.X1,self.X2))
        self.Y3 = np.concatenate((self.Y1,self.Y2))

    def ZeroAngle4(self):
        self.X4 = np.cos(self.ALIGN_ANGLE)*self.X3 - np.sin(self.ALIGN_ANGLE)*self.Y3
        self.Y4 = np.sin(self.ALIGN_ANGLE)*self.X3 + np.cos(self.ALIGN_ANGLE)*self.Y3

    def OneTooth(self):
        self.Internal()
        self.Parameters()
        self.InvoluteCurve()
        self.EdgeRoundCurve()
        self.RootRoundCurve()
        self.OuterArc()
        self.RootArc()
        self.Reverse()
        self.Combine1()
        self.MirrorY()
        self.Combine3()
        self.ZeroAngle4()

    def TotalTeeth(self):
        Xtemp = []
        Ytemp = []
        for i in range(0,int(round(self.Z,6))):
            Xtemp = np.concatenate((Xtemp, np.cos(-self.P_ANGLE*i)*self.X4-np.sin(-self.P_ANGLE*i)*self.Y4))
            Ytemp = np.concatenate((Ytemp, np.sin(-self.P_ANGLE*i)*self.X4+np.cos(-self.P_ANGLE*i)*self.Y4))
        self.X5 = Xtemp
        self.Y5 = Ytemp

    def MovePositionOneTooth(self):
        self.X6 = self.X4 + self.X_0
        self.Y6 = self.Y4 + self.Y_0

    def RotateTotalTeeth(self):
        self.X7 = np.cos(np.deg2rad(self.ROTATE_ANGLE))*self.X5-np.sin(np.deg2rad(self.ROTATE_ANGLE))*self.Y5
        self.Y7 = np.sin(np.deg2rad(self.ROTATE_ANGLE))*self.X5+np.cos(np.deg2rad(self.ROTATE_ANGLE))*self.Y5

    def MovePositionTotalTeeth(self):
        self.X8 = self.X7 + self.X_0
        self.Y8 = self.Y7 + self.Y_0

    def PitchCircle(self):
        THETAp = np.linspace(0,2*np.pi,self.SEG_CIRCLE)
        RADIUSp = self.M*(self.Z+self.X)/2
        self.Xp = RADIUSp*np.cos(THETAp) + self.X_0
        self.Yp = RADIUSp*np.sin(THETAp) + self.Y_0

    def OuterCircle(self):
        THETAo = np.linspace(0,2*np.pi,self.SEG_CIRCLE)
        RADIUSo = self.M*(self.Z+self.X)/2 + self.M*self.A
        self.Xo = RADIUSo*np.cos(THETAo) + self.X_0
        self.Yo = RADIUSo*np.sin(THETAo) + self.Y_0

    def RootCircle(self):
        THETAr = np.linspace(0,2*np.pi,self.SEG_CIRCLE)
        RADIUSr = self.M*(self.Z+self.X)/2 - self.M*self.D
        self.Xr = RADIUSr*np.cos(THETAr) + self.X_0
        self.Yr = RADIUSr*np.sin(THETAr) + self.Y_0

    def Calc(self):
        self.OneTooth()
        self.TotalTeeth()
        self.MovePositionOneTooth()
        self.RotateTotalTeeth()
        self.MovePositionTotalTeeth()
        self.PitchCircle()
        self.OuterCircle()
        self.RootCircle()

"""
G1 = GPG()
G1.Calc()
"""