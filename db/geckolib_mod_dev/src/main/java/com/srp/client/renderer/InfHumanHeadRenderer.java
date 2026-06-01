package com.srp.client.renderer;

import com.srp.client.model.InfHumanHeadModel;
import com.srp.entity.InfHumanHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfHumanHeadRenderer extends GeoEntityRenderer<InfHumanHeadEntity> {

    public InfHumanHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfHumanHeadModel());
    }
}
