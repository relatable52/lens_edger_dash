// --- 1. Lens Parameters ---
const lensParams = {
R1: 500,          // Front curve radius (mm)
R2: 100,          // Back curve radius (mm)
diameter: 70,    // Lens diameter (mm)
thickness: 2,   // Center thickness (mm)
resolution: 0.2  
};

// --- 2. Setup VTK Rendering Environment ---
const fullScreenRenderer = vtk.Rendering.Misc.vtkFullScreenRenderWindow.newInstance({
rootContainer: document.querySelector('#container'),
background: [0.2, 0.2, 0.2], // Dark grey background
});
const renderer = fullScreenRenderer.getRenderer();
const renderWindow = fullScreenRenderer.getRenderWindow();

// --- 3. Create vtkImageData (The Volume) ---
const imageData = vtk.Common.DataModel.vtkImageData.newInstance();

// Calculate bounds to ensure the grid covers the whole lens
const xyboundsSize = lensParams.diameter + 10;
const zboundsSize = lensParams.R2 - Math.sqrt(lensParams.R2**2 - (lensParams.diameter/2)**2) + lensParams.thickness + 10;
const xydim = Math.ceil(xyboundsSize / lensParams.resolution);
const zdim = Math.ceil(zboundsSize / lensParams.resolution);

imageData.setDimensions(xydim, xydim, zdim);
// Spacing determines the physical size of each voxel
const spacing = [lensParams.resolution, lensParams.resolution, lensParams.resolution];
imageData.setSpacing(spacing);
// Origin places the center of the volume at (0,0,0)
imageData.setOrigin(
    - (xydim * spacing[0]) / 2, 
    - (xydim * spacing[1]) / 2, 
    0
);

// --- 4. Procedural Generation Logic (with Soft Edges) ---
const dataArray = new Float32Array(xydim * xydim * zdim);

// Centers of the two spheres
const zC1 = lensParams.R1;
const zC2 = (lensParams.thickness / 2) + lensParams.R2;

// Pre-calculate squared radii
const r1Sq = lensParams.R1 ** 2;
const r2Sq = lensParams.R2 ** 2;
const cylRSq = (lensParams.diameter / 2) ** 2;

// This defines how "soft" the edge is (in mm). 
// 0.5 * voxel resolution is usually good for anti-aliasing.
const smoothEdge = lensParams.resolution * 0.8; 

let iter = 0;
for (let z = 0; z < zdim; z++) {
  const physZ = imageData.getOrigin()[2] + z * spacing[2];
  
  for (let y = 0; y < xydim; y++) {
    const physY = imageData.getOrigin()[1] + y * spacing[1];
    
    for (let x = 0; x < xydim; x++) {
      const physX = imageData.getOrigin()[0] + x * spacing[0];

      // --- Distance Field Calculation ---
      
      // 1. Distance to Cylinder (XY Plane)
      // d = distance from center - radius
      const distFromCenter = Math.sqrt(physX*physX + physY*physY);
      const distCyl = distFromCenter - (lensParams.diameter / 2);

      // 2. Distance to Front Sphere (Convex)
      // d = distance from sphere center - radius
      const distSphere1 = Math.sqrt(physX*physX + physY*physY + (physZ - zC1)**2) - lensParams.R1;

      // 3. Distance to Back Sphere (Concave/Meniscus logic)
      // Note: For the "Cutout" shape you used (distSq2 >= R2), we want the distance *from* the void.
      // We invert the sign effectively. 
      const distToSphere2Center = Math.sqrt(physX*physX + physY*physY + (physZ - zC2)**2);
      // We want to be OUTSIDE this sphere, so "inside" the lens means distance > radius.
      // We flip this so that negative numbers mean "inside lens material".
      const distSphere2 = lensParams.R2 - distToSphere2Center; 

      // INTERSECTION: The point is inside the lens if it is:
      // Inside Cyl AND Inside Sphere1 AND Outside Sphere2
      // In Signed Distance Fields (SDF), Intersection = max(d1, d2, d3)
      const maxDist = Math.max(distCyl, distSphere1, distSphere2);

      // --- Map Distance to Density ---
      // If maxDist is negative, we are inside. If positive, outside.
      // We map this to 0..100 with a small transition zone for smoothness.
      
      let value = 0;
      if (maxDist < 0) {
        // Inside lens material
        value = 100;
      }

      dataArray[iter] = value;
      iter++;
    }
  }
}

// Attach data to imageData
const scalarArray = vtk.Common.Core.vtkDataArray.newInstance({
name: 'Scalars',
values: dataArray,
});
imageData.getPointData().setScalars(scalarArray);

// --- 5. Create Volume Pipeline ---
const actor = vtk.Rendering.Core.vtkVolume.newInstance();
const mapper = vtk.Rendering.Core.vtkVolumeMapper.newInstance();
mapper.setInputData(imageData);
actor.setMapper(mapper);
// --- 6. Styling (Transfer Functions) ---

// Opacity: Air (0) is transparent, Lens (100) is semi-opaque
const ofun = vtk.Common.DataModel.vtkPiecewiseFunction.newInstance();
ofun.addPoint(0, 0.0);
ofun.addPoint(90, 0.0); // Sharp transition
ofun.addPoint(100, 0.3); // 0.3 opacity for a "glassy" look

// Color: Give it a nice optical blue/cyan tint
const cfun = vtk.Rendering.Core.vtkColorTransferFunction.newInstance();
cfun.addRGBPoint(0, 0.0, 0.0, 0.0);
cfun.addRGBPoint(100, 0.0, 0.8, 1.0); // Cyan glass

actor.getProperty().setRGBTransferFunction(0, cfun);
actor.getProperty().setScalarOpacity(0, ofun);
// Enable shading/lighting
actor.getProperty().setShade(true);
actor.getProperty().setAmbient(0.5);
actor.getProperty().setDiffuse(0.5);
actor.getProperty().setSpecular(0.5);
actor.getProperty().setSpecularPower(3.0);


// Enable interpolation for smoother look
actor.getProperty().setInterpolationTypeToLinear();

renderer.addVolume(actor);
renderer.resetCamera();
renderWindow.render();

console.log("Lens Generated");