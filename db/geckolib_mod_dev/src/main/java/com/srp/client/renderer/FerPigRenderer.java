package com.srp.client.renderer;

import com.srp.client.model.FerPigModel;
import com.srp.entity.FerPigEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerPigRenderer extends GeoEntityRenderer<FerPigEntity> {

    public FerPigRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerPigModel());
    }
}
