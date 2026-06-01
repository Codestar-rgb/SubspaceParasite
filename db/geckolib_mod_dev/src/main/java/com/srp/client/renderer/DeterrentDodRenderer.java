package com.srp.client.renderer;

import com.srp.client.model.DeterrentDodModel;
import com.srp.entity.DeterrentDodEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DeterrentDodRenderer extends GeoEntityRenderer<DeterrentDodEntity> {

    public DeterrentDodRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DeterrentDodModel());
    }
}
