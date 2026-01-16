window.vtkManager = {
    isInitialized: false,
    components: {},

    init: function(containerId) {
        const container = document.getElementById(containerId);
        if (!container || this.isInitialized) return;

        // Core Setup - Runs Only Once
        const renderWindow = vtk.Rendering.Core.vtkRenderWindow.newInstance();
        const renderer = vtk.Rendering.Core.vtkRenderer.newInstance();
        renderWindow.addRenderer(renderer);

        const apiView = renderWindow.newAPISpecificView();
        renderWindow.addView(apiView);
        apiView.setContainer(container);

        const interactor = vtk.Rendering.Core.vtkRenderWindowInteractor.newInstance();
        interactor.setView(apiView);
        interactor.initialize();
        interactor.bindEvents(container);
        interactor.setInteractorStyle(vtk.Interaction.Style.vtkInteractorStyleTrackballCamera.newInstance());

        // 1. Create Marching Cubes Filter (Isosurface Extraction)
        const marchingCube = vtk.Filters.General.vtkImageMarchingCubes.newInstance({
            contourValue: 500,        // Surface drawn at halfway point (0-1000 range)
            computeNormals: true,      // Required for proper lighting
            mergePoints: true          // Smoother mesh
        });

        // 2. Create Mapper (connects filter output to actor)
        const mapper = vtk.Rendering.Core.vtkMapper.newInstance();
        mapper.setInputConnection(marchingCube.getOutputPort());

        // 3. Create Actor (the visible object)
        const actor = vtk.Rendering.Core.vtkActor.newInstance();
        actor.setMapper(mapper);
        
        // 4. Configure Material Properties (like test_volume_2.html)
        const property = actor.getProperty();
        property.setColor(0.0, 0.8, 0.8);    // Cyan color
        property.setSpecular(0.8);            // Shiny highlights
        property.setSpecularPower(30);        // Sharp highlights
        property.setAmbient(0.2);             // Base ambient light
        property.setDiffuse(0.7);             // Matte surface lighting

        // Store references
        this.components = {
            renderWindow,
            renderer,
            apiView,
            interactor,
            actor,
            mapper,
            marchingCube
        };

        renderer.addActor(actor);
        
        // Add a default light so the shading isn't just black
        // renderer.createLight(); 

        this.isInitialized = true;
        
        // Resize observer logic...
        const resizeObserver = new ResizeObserver(() => {
            const dims = container.getBoundingClientRect();
            apiView.setSize(Math.floor(dims.width), Math.floor(dims.height));
            renderWindow.render();
        });
        resizeObserver.observe(container);

        console.log("VTK Manager initialized.");
    },

    updateData: function(volume_data) {
        if (!this.isInitialized) return;
        const { marchingCube, renderWindow, renderer } = this.components;

        // Store or create imageData
        if (!this.imageData) {
            this.imageData = vtk.Common.DataModel.vtkImageData.newInstance();
        }
        
        this.imageData.setDimensions(...volume_data.dimensions);
        this.imageData.setSpacing(...volume_data.spacing);
        this.imageData.setOrigin(...volume_data.origin);

        const scalarArray = vtk.Common.Core.vtkDataArray.newInstance({
            name: 'Scalars',
            values: new Float32Array(volume_data.scalars),
        });
        this.imageData.getPointData().setScalars(scalarArray);

        // Store reference for tool cutting
        this.dataArray = volume_data.scalars;
        this.dimensions = volume_data.dimensions;
        this.spacing = volume_data.spacing;
        this.origin = volume_data.origin;
        
        // Feed to marching cubes
        marchingCube.setInputData(this.imageData);
        
        // Reset camera only if it's the first data load
        if (!this.hasData) {
            renderer.resetCamera();
            this.hasData = true;
        }
        
        renderWindow.render();
    },

    setContourValue: function(value) {
        if (!this.isInitialized) return;
        const { marchingCube, renderWindow } = this.components;
        
        marchingCube.setContourValue(value);
        renderWindow.render();
    },

    loadToolMeshes: function(toolsData) {
        if (!this.isInitialized || !toolsData) return;
        const { renderer, renderWindow } = this.components;

        // Clear existing tool actors
        if (this.toolActors) {
            this.toolActors.forEach(actor => renderer.removeActor(actor));
        }
        this.toolActors = [];

        // Create actors for each tool
        toolsData.forEach(tool => {
            // Create polydata from points and polys
            const polydata = vtk.Common.DataModel.vtkPolyData.newInstance();
            
            // Set points
            const points = vtk.Common.Core.vtkPoints.newInstance();
            const pointsArray = new Float32Array(tool.points);
            points.setData(pointsArray, 3);
            polydata.setPoints(points);

            // Set polys (cell connectivity)
            const polys = vtk.Common.Core.vtkCellArray.newInstance();
            const polysArray = new Uint32Array(tool.polys);
            polys.setData(polysArray);
            polydata.setPolys(polys);

            // Create mapper
            const mapper = vtk.Rendering.Core.vtkMapper.newInstance();
            mapper.setInputData(polydata);

            // Create actor
            const actor = vtk.Rendering.Core.vtkActor.newInstance();
            actor.setMapper(mapper);
            
            // Set position and orientation
            actor.setPosition(tool.position[0], tool.position[1], tool.position[2]);
            actor.rotateY(-tool.tilt_angle);  // Apply tilt

            // Set material properties
            const property = actor.getProperty();
            property.setColor(0.7, 0.7, 0.7);  // Gray color for tools
            property.setSpecular(0.4);
            property.setSpecularPower(20);
            property.setAmbient(0.2);
            property.setDiffuse(0.8);

            renderer.addActor(actor);
            this.toolActors.push(actor);
        });

        renderWindow.render();
        console.log("Tool meshes loaded:", toolsData.length, "tools");
    },

    updateLensTransform: function(x, z, theta) {
        if (!this.isInitialized) return;
        const { actor, renderWindow } = this.components;

        // Reset orientation first
        actor.setOrientation(0, 0, theta);
        
        // Set position (x, y=0, z)
        actor.setPosition(x, 0, z);
    

        renderWindow.render();
    },

    // Helper to add a ground plane for reference
    addGroundPlane: function() {
        if (!this.isInitialized) return;
        const { renderer, renderWindow } = this.components;

        const planeSource = vtk.Filters.Sources.vtkPlaneSource.newInstance({
            xResolution: 1,
            yResolution: 1,
        });
        planeSource.setOrigin(-200, -200, -200);
        planeSource.setPoint1(200, -200, -200);
        planeSource.setPoint2(-200, 200, -200);

        const mapper = vtk.Rendering.Core.vtkMapper.newInstance();
        mapper.setInputConnection(planeSource.getOutputPort());

        const actor = vtk.Rendering.Core.vtkActor.newInstance();
        actor.setMapper(mapper);
        
        const property = actor.getProperty();
        property.setColor(0.7, 0.7, 0.7);
        property.setOpacity(0.4);

        renderer.addActor(actor);
        renderWindow.render();
    },
};