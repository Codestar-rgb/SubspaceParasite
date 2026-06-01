package com.srp.client.renderer;

import com.srp.client.model.UnvoModel;
import com.srp.entity.UnvoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class UnvoRenderer extends GeoEntityRenderer<UnvoEntity> {

    public UnvoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new UnvoModel());
    }
}
