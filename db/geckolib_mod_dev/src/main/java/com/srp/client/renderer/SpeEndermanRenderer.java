package com.srp.client.renderer;

import com.srp.client.model.SpeEndermanModel;
import com.srp.entity.SpeEndermanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeEndermanRenderer extends GeoEntityRenderer<SpeEndermanEntity> {

    public SpeEndermanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeEndermanModel());
    }
}
