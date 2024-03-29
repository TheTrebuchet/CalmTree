import math
from math import floor, ceil
import random
from mathutils import Vector, noise ,Matrix, Quaternion
import bl_math
from .helper import *

# bends the spine in a more meaningful way
def spine_bend(spine, n, bd_p, l, guide, mode):
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
    quat = old_vec.rotation_difference(new_vec)
    if mode == 'quat':
        return quat
    elif mode == 'spine':
        spine[-1] = quat@(spine[-1]-spine[-2])+spine[-2]
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
    
    return spine

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

    scale_list = [max(flare_f(i/n, flare_a)*radius, tipradius) for i in range(n)]

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

def guides_gen(spine, lim, m_p, br_p, t_p, qual):
    length, radius, tipradius = m_p[1:4]
    minang, maxang, start_h, horizontal, var, scaling, sd = br_p[1:]
    scale_f1, flare, scale_f2, shift = t_p
    
    if radius == tipradius:
        return []
    
    l = m_p[5]
    spine = spine[floor(start_h*len(spine)):]
    random.seed(sd)
    grid = [[]]
    orgs = []
    heights = []
    idx = len(spine)-2
    dist = 1/3*length*scaling
    ran = ceil(len(spine)/4)
    while idx>0:
        found = False
        for i in range(qual):
            npt, origin, h = ptgen(spine, dist, idx, scale_f1, flare, horizontal)
            if check(npt, grid, lim, idx, ran):
                grid[-1].append(npt)
                orgs.append(origin)
                heights.append(h)
                found = True
        if not found:
            idx-=1
            grid.append([])
    
    radii = lambda h, guide_l: min(max(scale_f1(h*(1-start_h)+start_h, flare)*radius*0.8, tipradius), guide_l/length*radius)
    lengthten = lambda h : length*scaling*scale_f2(h, shift)
    sol = [v for seg in [lis for lis in grid if lis] for v in seg]
    guides = [(sol[i] - orgs[i]).normalized()*lengthten(heights[i]) for i in range(len(sol))] #creating local guides and adjusting length
    
    for i in range(len(guides)):
        h = heights[i]
        ang = (math.pi/2-(h*minang+(1-h)*maxang))*random.uniform(1-var,1+var)
        guides[i] = Quaternion((spine[floor(h)]-spine[ceil(h)]).cross(guides[i]), ang)@guides[i]
    
    guidepacks = [[orgs[i],guides[i]*random.uniform(1-var, 1+var), radii(heights[i]/(1-start_h)-start_h, guides[i].length)] for i in range(len(orgs))] #creating guidepacks and radii
    return guidepacks

def fastguides_gen(spine, number, m_p, br_p, t_p):
    n = len(spine)
    length, radius, tipradius = m_p[1:4]
    minang, maxang, start_h, horizontal, var, scaling, br_seed = br_p[1:]
    scale_f1, flare, scale_f2, shift = t_p
    guidepacks = []
    random.seed(br_seed)
    chosen = pseudo_poisson_disc(number, length, radius)
    for i in range(number):
        height = chosen[i][1]*radius/length*(1-start_h)+start_h
        pick = math.floor(n*height)
        trans_vec = spine[pick]*(height*n-pick)+spine[pick]*(pick+1-height*n)
        x = (height-start_h)/(1-start_h)
        ang = minang*x+maxang*(1-x)
        ang += random.uniform(-var*ang,var*ang)
        a = chosen[i][0]
        quat = Vector((0,0,1)).rotation_difference(spine[pick]-spine[pick-1])
        dir_vec = Vector((math.sin(ang)*math.cos(a),math.sin(ang)*math.sin(a), math.cos(ang))).normalized()
        guide_vec = quat @ dir_vec
        guide_vec *= length*scaling*scale_f2(x, shift)*random.uniform(1-var, 1+var)
        guide_r = bl_math.clamp(scale_f1(height, flare)*radius*0.8, tipradius, guide_vec.length/length*radius)
        guidepacks.append((trans_vec, guide_vec, guide_r))
    return guidepacks

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
            self.spine = spine_bend(self.spine, self.n, self.bdp, self.mp[5], self.pack[1], 'spine')
        self.spine = spine_jiggle(self.spine, self.mp[5], self.mp[1], self.rp)
        self.spine = spine_weight(self.spine, self.n, self.mp[5], self.mp[2], self.trunk, self.bdp)

        self.spine = [vec+self.pack[0] for vec in self.spine]
        return self
    
    def regenerate(self):
        for i in range(2, self.n-1):
            quat = spine_bend(self.spine[i-2:i+1], self.n, self.bdp, self.mp[5], self.pack[1], 'quat')
            self.spine[i:] = [quat@(self.spine[k]-self.spine[i-1])+self.spine[i-1] for k in range(i,len(self.spine))]
        self.spine = spine_jiggle(self.spine, self.mp[5], self.mp[1], self.rp)
        self.spine = spine_weight(self.spine, self.n, self.mp[5], self.mp[2], self.trunk,self.bdp)
    
    def guidesgen(self, density, t_p, typ, qual):
        self.childmp = [int(max(self.mp[0]//2+1, 3)), self.mp[1], self.mp[2], self.mp[3], self.mp[4], self.mp[5]]
        if typ == 'fancy':
            self.guidepacks = guides_gen(self.spine, 1/density, self.mp, self.brp, t_p, qual)
        elif typ == 'fast':
            num = lambda d, l: ceil((2.2*l+11)*d**(1.37*l**0.1))
            self.guidepacks = fastguides_gen(self.spine, num(density, self.mp[1]), self.mp, self.brp, t_p)
    
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

def outgrow(branchlist, br_p, bn_p, bd_p, r_p, t_p, e_p):
    #creating the rest of levels
    for lev in range(br_p[0]):
        branchlist.append([])
        for parent in branchlist[-2]:
            parent.guidesgen(bn_p[lev], t_p, e_p[1], e_p[2])
            children = parent.guidepacks
            for pack in children:
                r_p[2] +=1
                bd_p[-1] +=1
                br_p[-1] +=1
                branchlist[-1].append(branch(pack, parent.childmp, bd_p, br_p, r_p, False).generate())
        br_p[3]=br_p[3]**2 #temporary workaround
    br_p[3]=br_p[3]**((0.5)**br_p[0]) 
    return branchlist

def toverts(branchlist, facebool, m_p, br_p, t_p, e_p):
    for lev in range(len(branchlist)-1):
        bran_i = 0
        while bran_i<len(branchlist[lev]):
            if branchlist[lev][bran_i].mp[2]==branchlist[lev][bran_i].mp[3]:
                branchlist[-1].insert(0, branchlist[lev].pop(bran_i))
            else:bran_i+=1


    #IF NOT FACEBOOL
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
        return verts, edges, [], [], []
    
    #FACEBOOL
    faces=[]
    
    #generating faces
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
    info=[]
    for lev in range(len(branchlist)):
        if lev == len(branchlist)-1:
            selection[0] = len(verts)
        for bran in branchlist[lev]:
            info.append([0,bran.mp[0]*bran.n-1, bran.mp[0]])
            verts.extend(bark_gen(bran.spine, bran.mp, t_p))
    
    selection = list(range(selection[0], len(verts)))
    
    for i in range(1,len(info)):
        info[i][0]=info[i-1][1]+1
        info[i][1]+=info[i][0]

    #flattening the base, 
    for lev in range(m_p[0]):
        verts[lev][2] = 0

    #scaling the tree
    verts = [vec*m_p[4] for vec in verts]
    
    return verts, [], faces, selection, info

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