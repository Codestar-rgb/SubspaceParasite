package com.srp.client.renderer;

import com.srp.client.model.DeterrentVenkrolModel;
import com.srp.entity.DeterrentVenkrolEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DeterrentVenkrolRenderer extends GeoEntityRenderer<DeterrentVenkrolEntity> {

    public DeterrentVenkrolRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DeterrentVenkrolModel());
    }
}
