package com.srp.client.renderer;

import com.srp.client.model.FerCowModel;
import com.srp.entity.FerCowEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerCowRenderer extends GeoEntityRenderer<FerCowEntity> {

    public FerCowRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerCowModel());
    }
}
