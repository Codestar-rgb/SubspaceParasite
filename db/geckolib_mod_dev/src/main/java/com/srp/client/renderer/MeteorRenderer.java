package com.srp.client.renderer;

import com.srp.client.model.MeteorModel;
import com.srp.entity.MeteorEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class MeteorRenderer extends GeoEntityRenderer<MeteorEntity> {

    public MeteorRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new MeteorModel());
    }
}
