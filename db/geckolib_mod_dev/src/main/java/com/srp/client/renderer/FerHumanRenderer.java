package com.srp.client.renderer;

import com.srp.client.model.FerHumanModel;
import com.srp.entity.FerHumanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerHumanRenderer extends GeoEntityRenderer<FerHumanEntity> {

    public FerHumanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerHumanModel());
    }
}
