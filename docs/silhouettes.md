In order to benefit from the silhouette tactile previews in 3DMake, you'll need to understand what they represent. The concept is not too complicated, but it isn't always intuitive either. This document will explain silhouettes non-visually with multiple examples that increase in complexity. There are 3D models for each example solid and silhouette described in this document, and it's a good idea to print them in order to feel their geometry. Before removing each object from your print bed, feel the object and note its orientation. 

### What is a silhouette?
A silhouette is a visual art form that depicts the outline of a person, or other object, when viewed from a certain angle, as if the object were between the viewer and a bright light source. Any rays of light from the light source that are blocked by the object leave a black space, so those areas are completely black. Other areas of the image are completely white. That means no details of the object's side facing the viewer are visible, only surface details that are on the outer edge of the object, perpendicular to the light source, will show up.

### Squished objects 
You can imagine a silhouette without referring to light sources. Imagine taking a 3D object and squishing it flat in one direction against a table, so that the object compresses in that direction without spreading out. If you were to squish a [sphere](#sphere-model) like this from any direction, you'd get a circle. By feeling this circle, you could determine the radius of the sphere.

Unlike spheres, most objects have different silhouettes depending on the viewing angle or "squishing direction". For example, if you put a [pyramid](#pyramid-model) flat on its base on the table and squished it this way, you'd get a square. But if you put it flat on its base and squished it against an upright wall, you'd get a triangle shape. In fact, most objects have an infinite number of different silhouettes depending on the viewing angle, or what we might call the "squishing angle".

Interestingly, if you balanced the same pyramid on its point and squished it down against the table, you'd get a square also. Take some time to convince yourself of this and understand why it's true. 

### Same object, different perspectives
Imagine a [doughnut](#doughnut-model) lying flat on a table. If we squish it down from the top, what do we get? The silhouette of the doughnut would be a ring shape; a flat circle with a circle cut out of the middle. If we feel this squished doughnut, we can tell the diameter of the overall doughnut, and the size of the interior hole.

However, if we squish the doughnut from its side against a wall instead, its "doughnut" shape is lost. We will get essentially a rectangle with rounded sides (on the left and right). This would let us examine the height of the doughnut. If there are sprinkles on top, we may be able to feel some irregular bumps on the top as well. But we won't know precisely where the sprinkles were.

### Hollow parts
Imagine a cylindrical [coffee mug](#mug-model) with a handle coming out of the right side. If we squish the coffee mug down from the top, we get a solid circle, with a little rectangle sticking out of the right. Despite the fact that the mug is hollow, and there's a hole in the handle, this information isn't represented in the top-down silhouette. Why not? 

If we squish the mug from the front against a wall, we'll get a rectangle for the main body, with half-circle ring on the right side for the handle. We could feel this to determine if there's enough space for our fingers to hold the handle.

However, one thing that no silhouette can tell us is that the mug is hollow. If we forgot to carve out the middle of the mug to hold coffee, the silhouettes from every single angle would be the same as a correctly hollowed out mug. Why? Because there is always an outer side to the cylindrical part of the mug from every angle. Imagine squishing the mug from different angles to convince yourself that this is true.

This mug example shows a key limitation of silhouettes. You can get a quick preview of the outer shape of an object from them, and catch some kinds of modelling mistakes, but they cannot represent "interior' features of an object.

### Mirror images
Here's a useful thing to know: The silhouette of an object viewed from an angle is actually a mirror image of the object's silhouette viewed from the opposite angle. Imagine taking the coffee mug silhouette from the front, with the handle on the right, and flipping it over on the table. The handle will be on the left, the same as if you walked around to the other side of the table and viewed the original mug from the back.

The same is true for an bottom-up silhouette - it's the top-down silhouette flipped. This is why 3DMake's default "3sil" preview doesn't produce a right side or bottom silhouette, you can get the same information from the left and top silhouettes.

Remember the pyramid from before? Since a pyramid's bottom is square, the top and bottom silhouettes are the same, since a square flipped over is still a square. That's why balancing the pyramid on its point and squishing it down produces the same silhouette.

## Models
All objects should be printed in the provided orientation. The silhouettes are thicker and have a taller top layer than those produced by 3DMake, so that they will be more resilient as a reference material.

- <a name="sphere-model" />**Sphere**: [original model](models/sphere.stl) [silhouette](models/sphere_topsil.stl) (note: this model will need supports)
- <a name="pyramid-model" />**Pyramid**: [original model](models/pyramid.stl) [top silhouette](models/pyramid_topsil.stl) [front silhouette](models/pyramid_frontsil.stl)
- <a name="doughnut-model" />**Doughnut**: [original model](models/doughnut.stl) [top silhouette](models/doughnut_topsil.stl) [front silhouette](models/doughnut_frontsil.stl)
- <a name="-mug-model" />**Mug**: [original model](models/mug.stl) [top silhouette](models/mug_topsil.stl) [front silhouette](models/mug_frontsil.stl)
