package com.srp.client.renderer;

import com.srp.client.model.InfectedInfHumanModel;
import com.srp.entity.InfectedInfHumanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfHumanRenderer extends GeoEntityRenderer<InfectedInfHumanEntity> {

    public InfectedInfHumanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfHumanModel());
    }
}
