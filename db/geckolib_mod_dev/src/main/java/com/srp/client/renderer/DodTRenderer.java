package com.srp.client.renderer;

import com.srp.client.model.DodTModel;
import com.srp.entity.DodTEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DodTRenderer extends GeoEntityRenderer<DodTEntity> {

    public DodTRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DodTModel());
    }
}
