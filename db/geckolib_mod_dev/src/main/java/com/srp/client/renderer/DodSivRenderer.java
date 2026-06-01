package com.srp.client.renderer;

import com.srp.client.model.DodSivModel;
import com.srp.entity.DodSivEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DodSivRenderer extends GeoEntityRenderer<DodSivEntity> {

    public DodSivRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DodSivModel());
    }
}
