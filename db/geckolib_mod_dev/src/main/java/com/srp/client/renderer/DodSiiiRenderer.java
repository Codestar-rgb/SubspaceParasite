package com.srp.client.renderer;

import com.srp.client.model.DodSiiiModel;
import com.srp.entity.DodSiiiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DodSiiiRenderer extends GeoEntityRenderer<DodSiiiEntity> {

    public DodSiiiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DodSiiiModel());
    }
}
