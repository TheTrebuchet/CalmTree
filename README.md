# TreeAddonProject

## Functions

the whole tree looks like this:

### tree_gen

- spine_gen
  - spine_init
  - spine_bend
- bark_gen
  - bark_circle
- bark_faces

descriptions

- `tree_gen` uses three functions below it to create a trunk
- `spine_gen` uses two functions to create a list of vertices that resemble a spine
- `spine_init` creates a list of points controlled by perlin parameters and main parameters, it is already rotated according to the guide
- `bark_gen` creates circles along the spine. Scaling is controlled by executable file functions and rotation controlled by the spine and guide
- `bark_circle` just creates a circle
- `bark_faces` creates link between points to form faces, it only needs number of sides and number of vertices on the spine

### branch_gen

- tree_gen

branch_gen uses tree_gen to create "trunks" on the main trunk, everything is controlled by guides outputted by the tree_gen

## config file basics

### main parameters

- sides
- length
- radius
- scale

### random parameters

- perlin
- perlin_amount
- perlin_scale
- perlin_seed

- bends_amount
- bends_angle
- bends_correction
- bends_scale
- bends_seed

### branch parameters

- branch_number
- branch_angle
- branch_height
- branch_weight
- branch_variety
- branch_seed
