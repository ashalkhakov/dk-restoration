# Pinned skin

`<character>.txt` pins vertexes to bones by hand, where the rigger's own choice is wrong. A line a vertex:

```
<surface>:<index> <bone> [<blend bone> <weight>]   # why
```

The rigger writes the whole table next to the rigged model, `dkres/models/rigged/<character>_skin.txt`:
- every vertex: its surface and index, its bone, the bone it blends with and the weight;
- how far it lands from Daikatana's on average and at worst;
- where it rests.

Find a vertex there and copy its `surface:index` here. Only numbers and names go in these files, none of Daikatana's
data.
