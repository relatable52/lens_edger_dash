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

        // 1. Create Actor and Mapper
        const volume = vtk.Rendering.Core.vtkVolume.newInstance();
        const mapper = vtk.Rendering.Core.vtkVolumeMapper.newInstance();
        volume.setMapper(mapper);

        // 2. CONFIGURE SHADING PROPERTIES
        const property = volume.getProperty();
        
        // Enable shading (this tells VTK to use the light sources)
        property.setShade(true);
        
        // Material Properties (Adjust these for your lens material)
        property.setAmbient(0.5);       // Base light (0.0 - 1.0)
        property.setDiffuse(0.5);       // Matte surface lighting
        property.setSpecular(0.5);      // Shiny highlights
        property.setSpecularPower(3);  // How sharp the highlight is (higher = sharper)
        
        // Critical for smooth look
        property.setInterpolationTypeToLinear();

        // 3. Setup default Opacity/Color (otherwise shading is hard to see)
        const ofun = vtk.Common.DataModel.vtkPiecewiseFunction.newInstance();
        ofun.addPoint(0, 0.0);
        ofun.addPoint(90, 0.0);
        ofun.addPoint(100, 0.3); // Adjust based on your lens scalar range
        property.setScalarOpacity(0, ofun);

        const cfun = vtk.Rendering.Core.vtkColorTransferFunction.newInstance();
        cfun.addRGBPoint(0, 0, 0, 0);
        cfun.addRGBPoint(100, 0.5, 0.8, 1.0); // Light blue/cyan for lens
        property.setRGBTransferFunction(0, cfun);

        // Store references
        this.components = {
            renderWindow,
            renderer,
            apiView,
            interactor,
            volume,
            mapper
        };

        renderer.addVolume(volume);
        
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
        const { mapper, renderWindow, renderer } = this.components;

        const imageData = vtk.Common.DataModel.vtkImageData.newInstance();
        imageData.setDimensions(...volume_data.dimensions);
        imageData.setSpacing(...volume_data.spacing);
        imageData.setOrigin(...volume_data.origin);

        const scalarArray = vtk.Common.Core.vtkDataArray.newInstance({
            name: 'Scalars',
            values: new Float32Array(volume_data.scalars),
        });
        imageData.getPointData().setScalars(scalarArray);

        console.log(imageData);
        
        // Just swap the data, don't recreate the whole scene
        mapper.setInputData(imageData);
        
        // Reset camera only if it's the first data load
        if (!this.hasData) {
            renderer.resetCamera();
            this.hasData = true;
        }
        
        renderWindow.render();
    }
};