import math
from math import floor, ceil
import random
from mathutils import Vector, noise ,Matrix, Quaternion
import bl_math
from .helper import *

# bends the spine in a more meaningful way
def spine_bend(spine, n, bd_p, l, guide, quatmode=False, nfactor=False):
    b_a, b_up, b_c, b_s, b_w, b_seed = bd_p
    f_noise = lambda i, b_seed: b_a*noise.noise((0, b_seed, i*l*b_s))
    old_vec = spine[-2] - spine[-3] #get previous vector
    angle = (Vector((0,0,1)).angle(old_vec)) #calculate global angle
    progress = 0
    if nfactor: progress = b_up*angle/n
    else: progress = b_up*angle/(n-len(spine)+1)
    quat = Quaternion(Vector((old_vec[1], -old_vec[0],0)), progress) #ideal progression
    new_vec = quat@old_vec
    
    bend_vec = Vector((f_noise(len(spine)-2, b_seed), f_noise(len(spine)-2, b_seed+10), 1)).normalized() #generate random vector        
    bend_vec = (Vector((0,0,1)).rotation_difference(new_vec))@bend_vec #rotating bend_vec to local direction
    x = bl_math.clamp(guide.angle(bend_vec,0.0)/math.radians(90))**2 #apply dampening, to be improved
    new_vec = bend_vec*(1-x) + new_vec.normalized()*x #mixing between random (bend_vec) and ideal (new_vec) vectors

    # transformation itself, rotating the remaining branch towards the new vector
    quat = old_vec.rotation_difference(new_vec)
    if quatmode:
        return quat
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

def bark_gen(spine, m_p, scale_f1, H=0):
    # parameters
    sides, radius, tipradius = m_p[0], m_p[2], m_p[3]
    
    n = len(spine)

    scale_list = [max(scale_f1(i/n*(1-H)+H)/scale_f1(H)*radius, tipradius) for i in range(n)]

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

def guides_gen(spine, m_p, pars, lev):
    #uses check and ptgen in helper
    lim = 1/pars.bn_p[lev]
    length, radius, tipradius = m_p[1:4]
    minang, maxang, start_h, horizontal, var, scaling, sd = pars.br_p[1:]
    qual = pars.e_p[2]
    scale_f1, scale_f2 = pars.scale_f1, pars.scale_f2
    
    if radius == tipradius:
        return []
    
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
            npt, origin, h = ptgen(spine, dist, idx, scale_f1, horizontal)
            if check(npt, grid, lim, idx, ran):
                grid[-1].append(npt)
                orgs.append(origin)
                heights.append(h)
                found = True
        if not found:
            idx-=1
            grid.append([])
    
    radii = lambda h, guide_l: min(max(scale_f1(h*(1-start_h)+start_h)*radius*0.8, tipradius), guide_l/length*radius)
    lengthten = lambda h : length*scaling*scale_f2(h)
    sol = [v for seg in [lis for lis in grid if lis] for v in seg]
    guides = [(sol[i] - orgs[i]).normalized()*lengthten(heights[i]) for i in range(len(sol))] #creating local guides and adjusting length
    
    for i in range(len(guides)):
        h = heights[i]
        ang = (math.pi/2-(h*minang+(1-h)*maxang))*random.uniform(1-var,1+var)
        guides[i] = Quaternion((spine[floor(h)]-spine[ceil(h)]).cross(guides[i]), ang)@guides[i]
    
    guidepacks = [[orgs[i],guides[i]*random.uniform(1-var, 1+var), radii(heights[i]/(1-start_h)-start_h, guides[i].length)] for i in range(len(orgs))] #creating guidepacks and radii
    return guidepacks

def fastguides_gen(spine, number, m_p, br_p, t_p):
    #uses pseudo_poisson_disc in helper
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