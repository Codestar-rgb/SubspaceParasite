package com.srp.client.renderer;

import com.srp.client.model.InfHumanModel;
import com.srp.entity.InfHumanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfHumanRenderer extends GeoEntityRenderer<InfHumanEntity> {

    public InfHumanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfHumanModel());
    }
}
