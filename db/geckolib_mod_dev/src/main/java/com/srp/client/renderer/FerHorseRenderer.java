package com.srp.client.renderer;

import com.srp.client.model.FerHorseModel;
import com.srp.entity.FerHorseEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerHorseRenderer extends GeoEntityRenderer<FerHorseEntity> {

    public FerHorseRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerHorseModel());
    }
}
