package com.srp.client.renderer;

import com.srp.client.model.SpeHumanModel;
import com.srp.entity.SpeHumanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeHumanRenderer extends GeoEntityRenderer<SpeHumanEntity> {

    public SpeHumanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeHumanModel());
    }
}
