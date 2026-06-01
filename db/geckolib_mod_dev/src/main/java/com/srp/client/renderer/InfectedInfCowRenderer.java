package com.srp.client.renderer;

import com.srp.client.model.InfectedInfCowModel;
import com.srp.entity.InfectedInfCowEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfCowRenderer extends GeoEntityRenderer<InfectedInfCowEntity> {

    public InfectedInfCowRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfCowModel());
    }
}
