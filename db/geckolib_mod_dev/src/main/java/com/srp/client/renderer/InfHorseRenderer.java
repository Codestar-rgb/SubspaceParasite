package com.srp.client.renderer;

import com.srp.client.model.InfHorseModel;
import com.srp.entity.InfHorseEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfHorseRenderer extends GeoEntityRenderer<InfHorseEntity> {

    public InfHorseRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfHorseModel());
    }
}
