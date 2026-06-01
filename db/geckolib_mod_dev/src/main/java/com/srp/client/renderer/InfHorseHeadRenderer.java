package com.srp.client.renderer;

import com.srp.client.model.InfHorseHeadModel;
import com.srp.entity.InfHorseHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfHorseHeadRenderer extends GeoEntityRenderer<InfHorseHeadEntity> {

    public InfHorseHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfHorseHeadModel());
    }
}
