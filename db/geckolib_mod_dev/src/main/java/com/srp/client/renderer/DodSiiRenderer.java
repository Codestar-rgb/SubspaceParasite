package com.srp.client.renderer;

import com.srp.client.model.DodSiiModel;
import com.srp.entity.DodSiiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DodSiiRenderer extends GeoEntityRenderer<DodSiiEntity> {

    public DodSiiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DodSiiModel());
    }
}
