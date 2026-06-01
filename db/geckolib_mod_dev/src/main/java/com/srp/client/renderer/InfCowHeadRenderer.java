package com.srp.client.renderer;

import com.srp.client.model.InfCowHeadModel;
import com.srp.entity.InfCowHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfCowHeadRenderer extends GeoEntityRenderer<InfCowHeadEntity> {

    public InfCowHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfCowHeadModel());
    }
}
