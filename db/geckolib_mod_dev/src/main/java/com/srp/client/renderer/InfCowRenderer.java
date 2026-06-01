package com.srp.client.renderer;

import com.srp.client.model.InfCowModel;
import com.srp.entity.InfCowEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfCowRenderer extends GeoEntityRenderer<InfCowEntity> {

    public InfCowRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfCowModel());
    }
}
