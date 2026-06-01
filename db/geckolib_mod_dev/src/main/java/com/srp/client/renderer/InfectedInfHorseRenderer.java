package com.srp.client.renderer;

import com.srp.client.model.InfectedInfHorseModel;
import com.srp.entity.InfectedInfHorseEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfHorseRenderer extends GeoEntityRenderer<InfectedInfHorseEntity> {

    public InfectedInfHorseRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfHorseModel());
    }
}
