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

    setContourValue: function(value, time_length) {
        if (!this.isInitialized) return;
        const { marchingCube, renderWindow } = this.components;
        
        marchingCube.setContourValue(1000 - time_length + value);
        renderWindow.render();
    },
};