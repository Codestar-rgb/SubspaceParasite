package com.srp.client.renderer;

import com.srp.client.model.AboHeadModel;
import com.srp.entity.AboHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AboHeadRenderer extends GeoEntityRenderer<AboHeadEntity> {

    public AboHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AboHeadModel());
    }
}
