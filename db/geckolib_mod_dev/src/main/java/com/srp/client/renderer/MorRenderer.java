package com.srp.client.renderer;

import com.srp.client.model.MorModel;
import com.srp.entity.MorEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class MorRenderer extends GeoEntityRenderer<MorEntity> {

    public MorRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new MorModel());
    }
}
