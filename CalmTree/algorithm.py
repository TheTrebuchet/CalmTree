import math
from math import floor, ceil
import random
from mathutils import Vector, noise ,Matrix, Quaternion
import bl_math
from .helper import *

# bends the spine in a more meaningful way
def spine_bend(spine, n, bd_p, l, guide):
    b_a, b_up, b_c, b_s, b_w, b_seed = bd_p
    f_noise = lambda i, b_seed: b_a*noise.noise((0, b_seed, i*l*b_s))
    
    old_vec = spine[-2] - spine[-3] #get previous vector
    angle = (Vector((0,0,1)).angle(old_vec)) #calculate global angle
    quat = Quaternion(Vector((old_vec[1], -old_vec[0],0)), b_up*angle/(n-len(spine)+1)) #ideal progression
    new_vec = quat@old_vec
    
    bend_vec = Vector((f_noise(len(spine)-2, b_seed), f_noise(len(spine)-2, b_seed+10), 1)).normalized() #generate random vector        
    bend_vec = (Vector((0,0,1)).rotation_difference(new_vec))@bend_vec #rotating bend_vec to local direction
    x = bl_math.clamp(guide.angle(bend_vec,0.0)/math.radians(90))**2 #apply dampening, to be improved
    new_vec = bend_vec*(1-x) + new_vec.normalized()*x #mixing between random (bend_vec) and ideal (new_vec) vectors

    # transformation itself, rotating the remaining branch towards the new vector
    trans1 = Matrix.Translation(-1*spine[-2])
    trans2 = Matrix.Translation(spine[-2])
    quat = old_vec.rotation_difference(new_vec)
    spine[-1] = (trans2@(quat@(trans1@spine[-1])))
    return spine

def spine_weight(spine, n, l, r, trunk, bd_p):
    b_c, b_w = bd_p[2], bd_p[4]

    weight = lambda x, ang: math.sin(ang)*(1-x)*l*n #it has influences from trunk working cross section, weight of the branch (without child-branches), angle of the branch

    for i in range(n-2):
        vec = spine[i] - spine[i-1] #get previous vector
        angle = (Vector((0,0,1)).angle(vec))
        CM_lis = [spine[v]*(1-(v)/n) for v in range(i+1,n)]
        CM = Vector((0,0,0))
        for v in CM_lis:
            CM += v
        CM = CM/((n-i-1)*(n-i)/(2*n))-spine[i]
        w_angle = CM[0]**2+CM[1]**2-(r*math.cos(angle))**2
        if w_angle<0: w_angle = 0
        w_angle = weight(i/n, math.atan(w_angle**0.5/(CM[2]+r*math.sin(angle))))
        
        trans1 = Matrix.Translation(-1*spine[i])
        trans2 = Matrix.Translation(spine[i])
        quat = Quaternion(Vector((vec[1], -vec[0],0)), -w_angle*b_w)
        spine[i:] = [trans2@(quat@(trans1@vec)) for vec in spine[i:]]

    if trunk:
        CM = Vector([sum([i[0] for i in spine])/n, sum([i[1] for i in spine])/n, sum([i[2] for i in spine])/n])
        quat = Quaternion(Vector((CM[1],-CM[0],0)), Vector((0,0,1)).angle(CM)*b_c)
        spine[:] = [quat@i for i in spine]

def spine_jiggle(spine, l, length, rp):
    p_a, p_s, p_seed = rp
    jigf = lambda z : p_a*(noise.noise(Vector([0, p_seed, p_s*z]))-0.5)
    st = spine[1]-spine[0]
    ref = []
    if st[0]!=st[1]:
        ref = st.cross(Vector((st[1],-st[0],0))).normalized()
    else:
        ref = st.cross(Vector((st[2],0,-st[0]))).normalized()
    for i in range(1,len(spine)):
        x = (st.rotation_difference(spine[i]-spine[i-1])@ref).normalized()
        y = x.cross(spine[i]-spine[i-1]).normalized()
        spine[i]+=x*(jigf(i*l)-jigf(0)) + y*(jigf(i*l+length)-jigf(length))
    return spine
# BARK
# number of sides, radius
def bark_circle(n,r):
    circle = []
    if n<3 or r==0:
        return []
    else:
        for i in range(n):
            circle.append(Vector((r*math.cos(2*math.pi*i/n), r*math.sin(2*math.pi*i/n), 0)))
    return circle

def bark_gen(spine, m_p, t_p):
    # parameters
    sides, radius, tipradius = m_p[0], m_p[2], m_p[3]
    flare_f, flare_a = t_p[:2]
    n = len(spine)

    scale_list = [bl_math.clamp(flare_f(i/n, flare_a)*radius, tipradius, radius) for i in range(n)]

    # generating bark with scaling and rotation based on parameters and spine
    quat = Vector((0,0,1)).rotation_difference(spine[1]-spine[0])
    bark = [(quat@i)+spine[0] for i in bark_circle(sides,scale_list[0])]
    
    for x in range(1, n-1):
        vec = spine[x+1] - spine[x-1]
        quat = Vector((0,0,1)).rotation_difference(vec)
        new_circle = [quat @ i for i in bark_circle(sides,scale_list[x])]
        for y in new_circle:
            bark.append((Vector(spine[x]) + Vector(y)))
    
    bark += [(quat@i + Vector(spine[-1])) for i in bark_circle(sides,scale_list[-1])]
    return bark

#number of sides, number of vertices, generates faces
def face_gen(s, n):
    faces = []
    for i in range(n-1):
        for j in range(s):
            if j != s-1:
                faces.append(tuple([j+s*i, j+1+s*i, j+1+(i+1)*s, j+(i+1)*s]))
            else:
                faces.append(tuple([j+s*i, s*i, s*(i+1), j+s*(i+1)]))
    
    return faces

# BRANCHES AND TREE GENERATION
# outputs [place of the branch, vector that gives branch angle and size, radius of the branch]

def guides_gen(spine, lim, m_p, br_p, t_p):
    length, radius, tipradius = m_p[1:4]
    minang, maxang, start_h, var, scaling, sd = br_p[1:]
    scale_f1, flare, scale_f2, shift = t_p
    l = m_p[5]
    spine = spine[floor(start_h*len(spine)):]
    random.seed(sd)
    k = 12
    grid = [[]]
    orgs = []
    heights = []
    idx = 0
    dist = 1/3*length*scaling
    ran = 10
    while idx<len(spine)-1:
        found = False
        for i in range(k):
            npt, origin, h = ptgen(spine, dist, idx, scale_f1, flare)
            if check(npt, grid, lim, idx, ran):
                grid[-1].append(npt)
                orgs.append(origin)
                heights.append(h)
                found = True
        if not found:
            idx+=1
            grid.append([])
    
    radii = lambda h, guide_l: min(max(scale_f1(h, flare)*radius*0.8, tipradius), guide_l/length*radius)
    lengthten = lambda h : length*scaling*scale_f2(h, shift)
            
    sol = [v for seg in [lis for lis in grid if lis] for v in seg]
    
    guides = [(sol[i] - orgs[i]).normalized()*lengthten(heights[i]) for i in range(len(sol))] #adjusting length
    
    for i in range(len(guides)):
        h = heights[i]
        ang = (math.pi/2-(h*minang+(1-h)*maxang))*random.uniform(1-var,1+var)
        guides[i] = Quaternion((spine[floor(h)]-spine[ceil(h)]).cross(guides[i]), ang)@guides[i]
        print(heights[i], scale_f1(heights[i], flare), radii(h, 1))
    
    guidepacks = [[orgs[i],guides[i]*random.uniform(1-var, 1+var), radii(heights[i], guides[i].length)*random.uniform(1-var, 1+var)] for i in range(len(orgs))] #creating guidepacks and radii

    return guidepacks

#generates a single trunk, whether it will be branch or the main trunk
class branch():
    def __init__(self, pack, m_p, bd_p, br_p, r_p, trunk):
        self.pack = pack
        self.mp = [m_p[0], self.pack[1].length, self.pack[2], m_p[3], m_p[4], bl_math.clamp(m_p[5], 0, self.pack[1].length/2)]
        self.bdp = bd_p
        self.brp = br_p
        self.rp = r_p
        self.trunk = trunk
        self.guidepacks=[]
        self.n = 0
        self.spine=[]
        
    def generate(self):
        self.n = round(self.mp[1]/self.mp[5])+1
        self.spine = [Vector((0,0,0))]
        self.spine.append((self.pack[1].normalized())*self.mp[5])

        while len(self.spine)<self.n:
            self.spine.append(self.mp[5]*((self.spine[-1] - self.spine[-2]).normalized())+self.spine[-1])
            spine_bend(self.spine, self.n, self.bdp, self.mp[5], self.pack[1])
        spine_jiggle(self.spine, self.mp[5], self.mp[1], self.rp)
        spine_weight(self.spine, self.n, self.mp[5], self.mp[2], self.trunk, self.bdp)

        self.spine = [vec+self.pack[0] for vec in self.spine]
        return self
    
    def regenerate(self):
        for i in range(self.n-2):
            spine_bend(self.spine, self.n, self.bdp, self.mp[5], self.pack[1])
        spine_jiggle(self.spine, self.mp[5], self.mp[1], self.rp)
        spine_weight(self.spine, self.n, self.mp[5], self.mp[2], self.trunk,self.bdp)
    
    def guidesgen(self, density, t_p):
        self.childmp = [int(max(self.mp[0]//2+1, 4)), self.mp[1], self.mp[2], self.mp[3], self.mp[4], self.mp[5]]
        self.guidepacks = guides_gen(self.spine, 1/density, self.mp, self.brp, t_p)
    
    def interpolate(self, lev):
        if len(self.spine)>3:
            sp = self.spine
            a=0.1
            for l in range(lev):
                pt = (0.5+a)*sp[1]+(0.5+a)*sp[2]-a*(sp[0]+sp[3])
                sp.insert(2, pt)
                i = 3
                while i<len(sp)-2:
                    pt = (0.5+a)*sp[i]+(0.5+a)*sp[i+1]-a*(sp[i-2]+sp[i+2])
                    sp.insert(i+1, pt)
                    i+=2
            self.spine = sp
            self.n = len(sp)

# THE MIGHTY TREE GENERATION

def outgrow(branchlist, br_p, bn_p, bd_p, r_p, t_p):
    #creating the rest of levels
    tim = 0
    for lev in range(br_p[0]):
        branchlist.append([])
        for parent in branchlist[-2]:
            parent.guidesgen(bn_p[lev], t_p)
            children = parent.guidepacks
            for pack in children:
                r_p[2] +=1
                bd_p[-1] +=1
                br_p[-1] +=1
                branchlist[-1].append(branch(pack, parent.childmp, bd_p, br_p, r_p, False).generate())
    print(tim)
    return branchlist

def toverts(branchlist, facebool, m_p, br_p, t_p, e_p):
    #if the user doesn't need faces I provide only a spine
    if not facebool:
        verts = []
        edges =[]
        for lev in branchlist:
            for bran in lev:
                if e_p[0]!=0:bran.interpolate(e_p[0])
                verts.extend(bran.spine)
                if edges: edges += [[n+edges[-1][1]+1,n+2+edges[-1][1]] for n in range(len(bran.spine))][:-1]
                else: edges += [(n,n+1) for n in range(len(bran.spine))][:-1]
        verts = [vec*m_p[4] for vec in verts] #scale update
        return verts, edges, [], []
    
    faces=[]

    #generating faces, needs branches
    for lev in range(br_p[0]+1):
        for bran in branchlist[lev]:
            if e_p[0]!=0:bran.interpolate(e_p[0])
            faces.append(face_gen(bran.mp[0], bran.n))
    #combining faces
    while True:
        if len(faces) == 1:
            faces = faces[0]
            break
        faces[0].extend([[i+max(faces[0][-1])+1 for i in tup] for tup in faces.pop(1)])
    
    #generating verts from spine and making selection
    verts = []
    selection=[0]
    for lev in range(len(branchlist)):
        if lev == len(branchlist)-1:
            selection[0] = len(verts)
        for bran in branchlist[lev]:
            verts.extend(bark_gen(bran.spine, bran.mp, t_p))
    selection = list(range(selection[0], len(verts)))

    #flattening the base, 
    for lev in range(m_p[0]):
        verts[lev][2] = 0

    #scaling the tree
    verts = [vec*m_p[4] for vec in verts]
    
    return verts, [], faces, selection

def branchinit(verts, m_p, bd_p, br_p, r_p):
    m_p[3]*=m_p[2]
    st_pack = (verts[0],(verts[1]-verts[0]).normalized()*m_p[1], m_p[2])
    bran = branch(st_pack, m_p, bd_p, br_p, r_p, True)
    bran.n = len(verts)
    bran.spine = verts
    bran.regenerate()
    return [[bran]]


if __name__ == "__main__":
    spine = [Vector((0.0, 0.0, 0.0)), Vector((-0.04053265228867531, 0.1525326669216156, 0.5666670203208923)), Vector((-0.05233679339289665, 0.2162090241909027, 1.1513268947601318)), Vector((0.08932508528232574, 0.07073953002691269, 1.7034058570861816)), Vector((0.3351735472679138, -0.1757250726222992, 2.1775729656219482)), Vector((0.603615939617157, -0.4416947364807129, 2.628371238708496)), Vector((0.9189794659614563, -0.7344887852668762, 3.0294179916381836)), Vector((1.2864696979522705, -1.0440350770950317, 3.3687584400177)), Vector((1.5507733821868896, -1.3234150409698486, 3.813856601715088)), Vector((1.4413506984710693, -1.4571164846420288, 4.376147747039795)), Vector((1.1136771440505981, -1.5123927593231201, 4.861530303955078)), Vector((0.7895124554634094, -1.5705634355545044, 5.3489251136779785)), Vector((0.40334513783454895, -1.6063776016235352, 5.791208267211914)), Vector((-0.05430370569229126, -1.612501621246338, 6.160719394683838)), Vector((-0.49577754735946655, -1.616670846939087, 6.549442768096924)), Vector((-0.767345666885376, -1.5683027505874634, 7.068993091583252)), Vector((-0.6747534275054932, -1.3740949630737305, 7.616468906402588)), Vector((-0.3822815418243408, -1.097188115119934, 8.04518985748291))]
    mp = [0, 10, 0.44, 0.01*0.44, 1.0, 10/30]
    brp = [2, math.pi*30/180, math.pi*60/180,0.3, 0.1, 0.3, 1]
    scale_lf1 = lambda x, a : 1/((x+1)**a)-(x/2)**a #this one is for trunk flare
    scale_lf2 = lambda x, a : ((1-(x-1)**2)/(a*(x-1)+1))**0.5  #this one is for branches scale
    tp = [scale_lf1, 1.0, scale_lf2, 0.7]
    print(guides_gen(spine, 1, mp, brp, tp))