package com.srp.client.renderer;

import com.srp.client.model.FerEndermanModel;
import com.srp.entity.FerEndermanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerEndermanRenderer extends GeoEntityRenderer<FerEndermanEntity> {

    public FerEndermanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerEndermanModel());
    }
}
